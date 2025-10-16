import streamlit as st
import nbformat
from openai import OpenAI
from bs4 import BeautifulSoup
import requests
import re
import base64
import tempfile
from gtts import gTTS

# ---------- Config ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
st.set_page_config(page_title="Lector Inclusivo", layout="wide")
st.title("🎧 Lector Inclusivo (.ipynb y RPubs) — controles accesibles")

# ---------- Helpers ----------
def clean_markdown_text(md_text: str) -> str:
    lines = md_text.splitlines()
    cleaned = []
    for ln in lines:
        ln_strip = ln.strip()
        if re.fullmatch(r"[#\-\* ]+$", ln_strip):
            continue
        ln_strip = re.sub(r"^[#]+\s*", "", ln_strip)
        if len(ln_strip) == 0:
            continue
        cleaned.append(ln_strip)
    return "\n".join(cleaned).strip()

def detectar_tipo_contenido(texto: str) -> str:
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    if re.search(r"^\s*\|.+\|\s*$", texto, flags=re.MULTILINE) or "<table" in texto:
        return "tabla"
    if "```" in texto or re.search(r"\bdef\b|\bfor\b|\bimport\b|\bggplot\b", texto):
        return "codigo"
    return "texto"

def describir_para_usuario(tipo: str, texto: str) -> str:
    if tipo == "texto":
        return None
    if tipo == "formula":
        prompt = (
            "Genera una única frase EXACTA con este formato:\n"
            "\"A continuación verás una fórmula. Esta trata sobre [explicación corta sin tecnicismos].\"\n"
            "No repitas símbolos ni leas la fórmula. Sé muy breve.\n\n"
            f"Contenido muestra:\n{text[:800]}"
        )
    elif tipo == "tabla":
        prompt = (
            "Primera línea EXACTA: \"A continuación verás una tabla con las siguientes columnas:\"\n"
            "Luego, lista cada columna con su tipo inferido en formato:\n"
            "- columna <nombre>, tipo <numérica/texto/identificador/fecha>\n"
            "Al final, si puedes, indica cuántas filas aproximadamente.\n\n"
            f"Contenido muestra (tabla o contexto):\n{text[:1500]}"
        )
    else:  # codigo
        prompt = (
            "Genera una frase breve que explique qué hace el bloque de código sin leer el código.\n\n"
            f"Contenido muestra:\n{text[:1200]}"
        )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    try:
        out = resp.choices[0].message.content.strip()
    except Exception:
        out = ""
    return out

def text_to_base64_mp3(text: str, lang="es") -> str:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
        tts = gTTS(text=text, lang=lang)
        tts.save(tmp.name)
        tmp.seek(0)
        mp3_bytes = tmp.read()
    b64 = base64.b64encode(mp3_bytes).decode("utf-8")
    return f"data:audio/mp3;base64,{b64}"

def extraer_bloques_desde_html(html_text: str):
    soup = BeautifulSoup(html_text, "html.parser")
    container = None
    selectors = ["article", "main", ".post", ".content", ".container", ".rpubs", "#content", ".page"]
    for sel in selectors:
        try:
            if sel.startswith(".") or sel.startswith("#"):
                found = soup.select_one(sel)
            else:
                found = soup.find(sel)
        except Exception:
            found = None
        if found:
            container = found
            break
    if container is None:
        container = soup.body or soup

    bloques = []
    for tag in container.find_all(["h1","h2","h3","h4","p","pre","table"], recursive=True):
        if tag.name == "table":
            headers = [th.get_text(" ", strip=True) for th in tag.find_all("th")]
            if not headers:
                first_row = tag.find("tr")
                if first_row:
                    headers = [td.get_text(" ", strip=True) for td in first_row.find_all("td")]
            text = " | ".join(headers) if headers else tag.get_text(" ", strip=True)
            tipo = "tabla"
        else:
            text = tag.get_text(" ", strip=True)
            if not text or len(text) < 3:
                continue
            tipo = "texto"
            if tag.name == "pre":
                tipo = "codigo"
            if re.search(r"\$.*\$|\\begin\{equation\}", text):
                tipo = "formula"
        text = clean_markdown_text(text)
        if not text:
            continue
        bloques.append((tipo, text))
    return bloques

def procesar_ipynb(filelike):
    nb = nbformat.read(filelike, as_version=4)
    bloques = []
    for cell in nb.cells:
        if cell.get("cell_type") == "markdown":
            texto = clean_markdown_text(cell.get("source", ""))
            if texto:
                tipo = detectar_tipo_contenido(texto)
                bloques.append((tipo, texto))
        elif cell.get("cell_type") == "code":
            source = cell.get("source", "").strip()
            if source:
                tipo = detectar_tipo_contenido(source)
                bloques.append((tipo, source))
    return bloques

# ---------- UI: inputs ----------
st.sidebar.header("Entrada")
op = st.sidebar.radio("Fuente:", ["Subir .ipynb", "Pegar enlace RPubs (HTML)"])
uploaded = None
rpubs_link = None
if op == "Subir .ipynb":
    uploaded = st.sidebar.file_uploader("Sube .ipynb", type=["ipynb"])
else:
    rpubs_link = st.sidebar.text_input("Pega enlace RPubs (https://...)")

# ---------- Preparar bloques ----------
bloques = []
fuente_id = None
if uploaded:
    try:
        bloques = procesar_ipynb(uploaded)
        fuente_id = uploaded.name
    except Exception as e:
        st.error(f"Error al procesar .ipynb: {e}")
elif rpubs_link:
    try:
        if not rpubs_link.startswith("http"):
            raise ValueError("Link inválido. Debe comenzar con http/https.")
        resp = requests.get(rpubs_link, timeout=15)
        resp.raise_for_status()
        bloques = extraer_bloques_desde_html(resp.text)
        fuente_id = rpubs_link
    except Exception as e:
        st.error(f"No se pudo procesar el enlace RPubs: {e}")

if not bloques:
    st.info("Sube un .ipynb o pega un enlace RPubs para comenzar.")
    st.stop()

# ---------- Estado (reinicio si cambia la fuente) ----------
if "fuente_actual" not in st.session_state or st.session_state.get("fuente_actual") != fuente_id:
    st.session_state.fuente_actual = fuente_id
    st.session_state.bloques = bloques
    st.session_state.index = 0
    st.session_state.audios = [None] * len(bloques)
    st.session_state.intros = [None] * len(bloques)
    st.session_state.play = True  # por defecto reproducir al cargar

# ---------- Generar audio on-demand ----------
def preparar_audio_para_indice(i):
    tipo, texto = st.session_state.bloques[i]
    if tipo == "texto":
        intro = None
        contenido_a_leer = texto
    else:
        intro = describir_para_usuario(tipo, texto)
        # construir texto a leer: intro (breve) + pausa corta + contenido recitado
        # Nota: para tablas el LLM ya debe entregar la estructura de columnas
        if intro:
            contenido_a_leer = intro + "\n\n" + texto
        else:
            contenido_a_leer = texto
    data_uri = text_to_base64_mp3(contenido_a_leer, lang="es")
    st.session_state.audios[i] = data_uri
    st.session_state.intros[i] = intro or ""

# preparar primer audio si no existe
if st.session_state.audios[st.session_state.index] is None:
    with st.spinner("Generando audio..."):
        preparar_audio_para_indice(st.session_state.index)

# ---------- Render principal ----------
idx = st.session_state.index
tipo_actual, texto_actual = st.session_state.bloques[idx]
intro_actual = st.session_state.intros[idx]
data_uri = st.session_state.audios[idx]

st.markdown(f"### Bloque {idx+1} / {len(st.session_state.bloques)} — tipo: {tipo_actual}")
st.text_area("Texto (vista previa):", texto_actual, height=160)

# Construir HTML del player con autoplay controlado por st.session_state.play
autoplay_attr = "autoplay" if st.session_state.play else ""
html_audio = f"""
<audio id="player" src="{data_uri}" controls {autoplay_attr} style="width:100%"></audio>
"""
st.components.v1.html(html_audio, height=80, scrolling=False)

# ---------- Controles (únicos y en el mismo lugar) ----------
col1, col2, col3 = st.columns([1,1,1])
with col1:
    if st.button("⬅️ Anterior"):
        if st.session_state.index > 0:
            st.session_state.index -= 1
            if st.session_state.audios[st.session_state.index] is None:
                preparar_audio_para_indice(st.session_state.index)
            # al cambiar de bloque, dejar play = True para autoplay del nuevo bloque
            st.session_state.play = True
            st.experimental_rerun()
with col2:
    # Toggle Play/Pause: cambia el flag 'play' y rerun para aplicar autoplay o no
    if st.button("⏯️ Pausa / Reproducir"):
        st.session_state.play = not st.session_state.play
        # Si ponemos play True, queremos que el audio nuevo inicie
        # Al hacer rerun, el player se renderizará con o sin autoplay
        st.experimental_rerun()
with col3:
    if st.button("➡️ Siguiente"):
        if st.session_state.index < len(st.session_state.bloques) - 1:
            st.session_state.index += 1
            if st.session_state.audios[st.session_state.index] is None:
                preparar_audio_para_indice(st.session_state.index)
            st.session_state.play = True
            st.experimental_rerun()


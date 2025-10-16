import streamlit as st
import nbformat
from openai import OpenAI
from bs4 import BeautifulSoup
import requests
import re
import io
import base64
import tempfile
from gtts import gTTS

# ---------- Config ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
st.set_page_config(page_title="Lector Inclusivo", layout="wide")
st.title("🎧 Lector Inclusivo (.ipynb y RPubs) — controles accesibles")

# ---------- Helpers ----------
def clean_markdown_text(md_text: str) -> str:
    """Quita prefijos de encabezado '#' y líneas vacías; devuelve texto limpio para leer."""
    lines = md_text.splitlines()
    cleaned = []
    for ln in lines:
        ln_strip = ln.strip()
        # ignorar líneas que solo contienen '#', '---', '***', etc.
        if re.fullmatch(r"[#\-\* ]+$", ln_strip):
            continue
        # quitar prefijo de heading: '#', '##', etc.
        ln_strip = re.sub(r"^[#]+\s*", "", ln_strip)
        # ignorar enlaces de navegación típicos
        if len(ln_strip) == 0:
            continue
        cleaned.append(ln_strip)
    return "\n".join(cleaned).strip()

def detectar_tipo_contenido(texto: str) -> str:
    """Detecta formula / tabla / codigo / texto (simple heurística)."""
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    if re.search(r"^\s*\|.+\|\s*$", texto, flags=re.MULTILINE) or re.search(r"<table", texto):
        return "tabla"
    if "```" in texto or re.search(r"\bdef\b|\bfor\b|\bimport\b|\bggplot\b", texto):
        return "codigo"
    return "texto"

def describir_para_usuario(tipo: str, texto: str) -> str:
    """Usa LLM para generar la frase introductoria (solo para formulas/tablas/codigo)."""
    if tipo == "texto":
        return texto  # leer tal cual
    if tipo == "formula":
        prompt = (
            "Genera una única frase exactamente con este formato:\n"
            "\"A continuación verás una fórmula. Esta trata sobre [explicación corta sin tecnicismos].\"\n"
            "No repitas símbolos, ni leas la fórmula. Sé muy breve.\n\n"
            f"Contenido muestra (útil para inferir):\n{text[:800]}"
        )
    elif tipo == "tabla":
        prompt = (
            "Genera una introducción y luego lista las columnas con su tipo inferido.\n"
            "Primera línea EXACTA: \"A continuación verás una tabla con las siguientes columnas:\"\n"
            "Después, cada columna en formato: \"- columna <nombre>, tipo <numérica/texto/identificador/fecha>\"\n"
            "Si puedes, al final indica cuántas filas aproximadamente.\n\n"
            f"Contenido muestra (tabla o texto cercano):\n{text[:1500]}"
        )
    else:  # codigo
        prompt = (
            "Genera una breve frase que diga qué hace este bloque de código, sin leer el código.\n"
            "Sé muy conciso, orientado a un usuario ciego.\n\n"
            f"Contenido muestra (codigo):\n{text[:1200]}"
        )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    # extraer texto de la respuesta
    try:
        out = resp.choices[0].message.content.strip()
    except Exception:
        out = ""
    return out

def text_to_base64_mp3(text: str, lang="es") -> str:
    """Genera mp3 con gTTS a bytes, devuelve data URI base64 para audio src."""
    # gTTS guarda a archivo; se genera en memoria usando NamedTemporaryFile
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
        tts = gTTS(text=text, lang=lang)
        tts.save(tmp.name)
        tmp.seek(0)
        mp3_bytes = tmp.read()
    b64 = base64.b64encode(mp3_bytes).decode("utf-8")
    return f"data:audio/mp3;base64,{b64}"

# ---------- RPubs parsing robusto ----------
def extraer_bloques_desde_html(html_text: str):
    """Extrae bloques útiles del HTML de RPubs: paragraphs, pre, tablas.
       Intenta seleccionar el artículo principal mediante selectores comunes."""
    soup = BeautifulSoup(html_text, "html.parser")

    # Buscamos el contenedor principal con selectores comunes
    container = None
    selectors = ["article", "main", ".post", ".content", ".container", ".rpubs", "#content", ".page"]
    for sel in selectors:
        if sel.startswith(".") or sel.startswith("#"):
            found = soup.select_one(sel)
        else:
            found = soup.find(sel)
        if found:
            container = found
            break
    if container is None:
        container = soup.body or soup  # fallback

    bloques = []
    # preferir p, pre, table, h1..h4
    for tag in container.find_all(["h1","h2","h3","h4","p","pre","table"], recursive=True):
        text = ""
        if tag.name == "table":
            # obtener filas y cabeceras
            headers = [th.get_text(" ", strip=True) for th in tag.find_all("th")]
            # si no hay th, intentar la primera fila como header
            if not headers:
                first_row = tag.find("tr")
                if first_row:
                    headers = [td.get_text(" ", strip=True) for td in first_row.find_all("td")]
            text = ""
            if headers:
                text = " | ".join(headers)
            else:
                # fallback: textual content
                text = tag.get_text(" ", strip=True)
            tipo = "tabla"
        else:
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            # evitar leer menús o footers cortos
            if len(text) < 3:
                continue
            tipo = "texto"
            if tag.name == "pre":
                tipo = "codigo"
            if re.search(r"\$.*\$|\\begin\{equation\}", text):
                tipo = "formula"

        # limpiar encabezados markdown-style
        text = clean_markdown_text(text)
        if not text:
            continue
        bloques.append((tipo, text))
    return bloques

# ---------- Procesamiento de .ipynb ----------
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
                # preferimos no leer el código completo, lo tratamos como 'codigo' y generamos intro
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
if uploaded:
    try:
        bloques = procesar_ipynb(uploaded)
    except Exception as e:
        st.error(f"Error al procesar .ipynb: {e}")
elif rpubs_link:
    try:
        # validación simple
        if not rpubs_link.startswith("http"):
            raise ValueError("Link inválido. Debe comenzar con http/https.")
        resp = requests.get(rpubs_link, timeout=15)
        resp.raise_for_status()
        bloques = extraer_bloques_desde_html(resp.text)
    except Exception as e:
        st.error(f"No se pudo procesar el enlace RPubs: {e}")

if not bloques:
    st.info("Sube un .ipynb o pega un enlace RPubs para comenzar.")
    st.stop()

# ---------- Mantener estado ----------
if "bloques" not in st.session_state or st.session_state.get("fuente_actual") != (uploaded.name if uploaded else rpubs_link):
    # nueva fuente -> reconstruir audios y reset índice
    st.session_state.bloques = bloques
    st.session_state.index = 0
    st.session_state.audios = [None] * len(bloques)
    st.session_state.intros = [None] * len(bloques)
    st.session_state.fuente_actual = uploaded.name if uploaded else rpubs_link

# ---------- Generar intro + audio (on demand, para no gastar tokens todo de golpe) ----------
# Para accesibilidad, generamos la intro con LLM si corresponde, y convertimos intro+contenido a audio
def preparar_audio_para_indice(i):
    tipo, texto = st.session_state.bloques[i]
    # si texto plano -> leer directamente (no llamar LLM)
    if tipo == "texto":
        intro = None
        contenido_a_leer = texto
    else:
        # generar introducción (LLM) — formato controlado por describir_para_usuario
        intro = describir_para_usuario(tipo, texto)
        # según lo pedido: primero intro muy simple, luego recitar el contenido
        contenido_a_leer = intro + "\n\n" + texto
    # generar base64 mp3
    data_uri = text_to_base64_mp3(contenido_a_leer, lang="es")
    st.session_state.audios[i] = data_uri
    st.session_state.intros[i] = intro or ""

# preparar primer audio si no existe
if st.session_state.audios[st.session_state.index] is None:
    with st.spinner("Generando audio..."):
        preparar_audio_para_indice(st.session_state.index)

# ---------- UI principal: descripción + reproductor con controles fijos ----------
idx = st.session_state.index
tipo_actual, texto_actual = st.session_state.bloques[idx]
intro_actual = st.session_state.intros[idx]
data_uri = st.session_state.audios[idx]

st.markdown(f"### Bloque {idx+1} / {len(st.session_state.bloques)} — tipo: {tipo_actual}")
# mostrar una caja con el texto (solo para quien pueda verlo)
st.text_area("Texto (vista previa, no leer prefijos):", texto_actual, height=180)

# HTML para el reproductor con botones controlables desde Python (botones llaman a funciones JS)
# Nota: los botones reales (Anterior/Pausa/Siguiente) se renderizan aquí para controlar el <audio> por id.
html_player = f"""
<div style="position:relative; width:100%; max-width:900px; margin:0 auto; padding:8px;">
  <audio id="player" src="{data_uri}" controls style="width:100%;" preload="auto"></audio>
  <div style="display:flex; justify-content:space-between; margin-top:8px;">
    <button onclick="window.parent.postMessage({{'streamlit':true,'action':'prev'}}, '*')" style="font-size:18px; padding:8px 16px;">⬅️ Anterior</button>
    <button id="playpause" onclick="(function(){{
        var p = document.getElementById('player'); 
        if(p.paused) {{ p.play(); this.innerText='⏸️ Pausar' }} else {{ p.pause(); this.innerText='▶️ Reproducir' }};
    }})()" style="font-size:18px; padding:8px 16px;">▶️ Reproducir</button>
    <button onclick="window.parent.postMessage({{'streamlit':true,'action':'next'}}, '*')" style="font-size:18px; padding:8px 16px;">➡️ Siguiente</button>
  </div>
</div>
"""

# render HTML (usa allow-scripts)
st.components.v1.html(html_player, height=160, scrolling=False)

# ---------- Manejo de mensajes postMessage desde JS (prev/next) ----------
# Streamlit escucha mensajes window.postMessage en la app mediante st.experimental_get_query_params hack no fiable;
# En vez de eso, usamos botones Streamlit ocultos que el usuario ciego no necesita ver, y un pequeño script que
# hace postMessage que Streamlit puede capturar con st.experimental_get_query_params no es confiable.
# Alternativa práctica: escuchar eventos mediante st.socket do not exist. Usaremos una solución simple:
# Proporcionamos botones visibles además para compatibilidad (los botones JS envían postMessage que no se recibe
# en Streamlit por seguridad), por eso también dejamos botones Streamlit clásicos abajo.

col1, col2, col3 = st.columns([1,1,1])
with col1:
    if st.button("⬅️ Anterior (teclado)"):
        if st.session_state.index > 0:
            st.session_state.index -= 1
            # preparar audio si no existe
            if st.session_state.audios[st.session_state.index] is None:
                preparar_audio_para_indice(st.session_state.index)
            st.experimental_rerun()
with col2:
    # botón para pausar/reanudar desde Streamlit: este desactiva/reproduce el audio descargado mostrando mensaje instructivo
    if st.button("⏸️ Pausa / Reanudar (uso del reproductor)"):
        st.info("Usa el control del reproductor para pausar o reanudar. El botón aquí es indicativo.")
with col3:
    if st.button("➡️ Siguiente (teclado)"):
        if st.session_state.index < len(st.session_state.bloques)-1:
            st.session_state.index += 1
            if st.session_state.audios[st.session_state.index] is None:
                preparar_audio_para_indice(st.session_state.index)
            st.experimental_rerun()



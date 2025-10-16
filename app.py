import streamlit as st
import nbformat
from openai import OpenAI
from gtts import gTTS
import tempfile
import base64
import re

# ---------------- CONFIG ----------------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
st.set_page_config(page_title="Lector Inclusivo (.ipynb)", layout="centered")
st.title("🎧 Lector Inclusivo — Archivos .ipynb")

# ---------------- UTILIDADES ----------------
def clean_markdown(text):
    """Elimina #, guiones, líneas vacías y símbolos irrelevantes"""
    lines = text.splitlines()
    cleaned = []
    for ln in lines:
        ln = re.sub(r"^[#>\-\*\d\.\s]+", "", ln).strip()
        if ln:
            cleaned.append(ln)
    return " ".join(cleaned).strip()

def detectar_tipo(text):
    """Detecta si el bloque es texto, fórmula o tabla"""
    if re.search(r"\$.*\$|\\begin\{equation\}", text):
        return "formula"
    if re.search(r"\|.+\|", text):
        return "tabla"
    return "texto"

def describir_para_usuario(tipo, texto):
    """Genera una descripción sencilla SOLO si es tabla o fórmula"""
    if tipo == "formula":
        prompt = (
            "Di exactamente una frase así: "
            "\"A continuación verás una fórmula. Esta trata sobre [explicación corta sin tecnicismos].\" "
            f"Contenido:\n{texto[:600]}"
        )
    elif tipo == "tabla":
        prompt = (
            "Primera línea: 'A continuación verás una tabla con las siguientes columnas:' "
            "Luego lista las columnas con su tipo (numérica, texto, identificador, fecha). "
            f"Contenido:\n{texto[:800]}"
        )
    else:
        return None

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return resp.choices[0].message.content.strip()

def text_to_audio(text):
    """Convierte texto en base64 MP3"""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
        tts = gTTS(text=text, lang="es")
        tts.save(tmp.name)
        tmp.seek(0)
        data = base64.b64encode(tmp.read()).decode("utf-8")
    return f"data:audio/mp3;base64,{data}"

def procesar_ipynb(filelike):
    """Extrae los bloques de texto del notebook"""
    nb = nbformat.read(filelike, as_version=4)
    bloques = []
    for cell in nb.cells:
        if cell["cell_type"] in ["markdown", "code"]:
            text = clean_markdown(cell.get("source", ""))
            if len(text) > 0:
                tipo = detectar_tipo(text)
                bloques.append((tipo, text))
    return bloques

# ---------------- INTERFAZ ----------------

st.markdown("#### 👋 Bienvenido")
st.markdown("Esta herramienta permite escuchar paso a paso el contenido de un archivo `.ipynb`. "
            "Sube el archivo y luego usa los botones para avanzar, retroceder o pausar la lectura.")

# Mensaje de voz guía (solo la primera vez)
if "intro_reproducida" not in st.session_state:
    intro_audio = text_to_audio(
        "Bienvenido al lector inclusivo. Por favor, selecciona un archivo Jupyter con extensión punto I P Y N B para comenzar."
    )
    st.session_state.intro_reproducida = True
    st.audio(intro_audio, format="audio/mp3")

uploaded = st.file_uploader("Selecciona tu archivo .ipynb", type=["ipynb"], label_visibility="visible")

if not uploaded:
    st.stop()

# Procesar archivo
try:
    bloques = procesar_ipynb(uploaded)
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    st.stop()

if not bloques:
    st.warning("No se encontraron celdas con texto en este archivo.")
    st.stop()

# Estado
if "index" not in st.session_state:
    st.session_state.index = 0
    st.session_state.audios = [None] * len(bloques)
    st.session_state.play = True

# ---------------- GENERAR AUDIO ----------------
def preparar_audio(idx):
    tipo, texto = bloques[idx]
    intro = describir_para_usuario(tipo, texto)
    if intro:
        contenido = intro + ". " + texto
    else:
        contenido = texto
    return text_to_audio(contenido)

# Prepara audio si no existe
if st.session_state.audios[st.session_state.index] is None:
    with st.spinner("Generando audio..."):
        st.session_state.audios[st.session_state.index] = preparar_audio(st.session_state.index)

# Mostrar texto actual
idx = st.session_state.index
tipo, texto = bloques[idx]
st.markdown(f"### Bloque {idx+1} / {len(bloques)} — tipo: {tipo}")
st.text_area("Contenido actual:", texto, height=160)

# Reproductor
audio_uri = st.session_state.audios[idx]
autoplay_attr = "autoplay" if st.session_state.play else ""
st.components.v1.html(
    f'<audio controls {autoplay_attr} src="{audio_uri}" style="width:100%;"></audio>',
    height=80,
)

# ---------------- CONTROLES ----------------
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("⬅️ Anterior", use_container_width=True):
        if st.session_state.index > 0:
            st.session_state.index -= 1
            st.session_state.play = True
            if st.session_state.audios[st.session_state.index] is None:
                st.session_state.audios[st.session_state.index] = preparar_audio(st.session_state.index)
            st.experimental_rerun()

with col2:
    if st.button("⏯️ Pausa / Reproducir", use_container_width=True):
        st.session_state.play = not st.session_state.play
        st.experimental_rerun()

with col3:
    if st.button("➡️ Siguiente", use_container_width=True):
        if st.session_state.index < len(bloques) - 1:
            st.session_state.index += 1
            st.session_state.play = True
            if st.session_state.audios[st.session_state.index] is None:
                st.session_state.audios[st.session_state.index] = preparar_audio(st.session_state.index)
            st.experimental_rerun()



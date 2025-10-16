import streamlit as st
import nbformat
from openai import OpenAI
import re
import time

# Inicializar cliente de OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="🎧 Lector Inclusivo de Notebooks", layout="centered")

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")
st.write("""
Esta aplicación convierte notebooks de Jupyter en una experiencia auditiva accesible.
Usa los siguientes botones grandes para navegar:
- **Anterior**: Regresa al bloque anterior.
- **Reproducir / Pausar**: Inicia o pausa el audio.
- **Siguiente**: Avanza al siguiente bloque.
""")

uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

# -------------------------
# Detección del tipo de contenido
# -------------------------
def detectar_tipo_contenido(texto):
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):
        return "tabla"
    else:
        return "texto"

# -------------------------
# Descripción guiada según tipo
# -------------------------
def describir_contenido(tipo, texto):
    if tipo == "formula":
        prompt = f"""
        Eres un asistente que apoya a personas ciegas leyendo notebooks.
        Di: "A continuación verás una fórmula. Esta trata sobre [tema general de la fórmula, sin símbolos]."
        Contenido: {texto[:800]}
        """
    elif tipo == "tabla":
        prompt = f"""
        Eres un asistente que apoya a personas ciegas leyendo notebooks.
        El contenido es una tabla. 
        Di: "A continuación verás una tabla con las siguientes columnas:" 
        Luego menciona cada columna y su tipo (numérica, texto, identificador, etc.).
        Contenido: {texto[:1000]}
        """
    elif tipo == "código":
        prompt = f"""
        Eres un asistente que apoya a personas ciegas leyendo notebooks.
        El contenido es una celda de código Python. 
        Di brevemente qué hace el código, sin leerlo línea por línea.
        Contenido: {texto[:800]}
        """
    else:
        prompt = texto

    if tipo == "texto":
        return prompt
    else:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        return response.choices[0].message.content

# -------------------------
# Conversión texto a voz
# -------------------------
def text_to_speech(text):
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return audio_response.read()

# -------------------------
# Control de navegación
# -------------------------
if "bloques" not in st.session_state:
    st.session_state.bloques = []
if "index" not in st.session_state:
    st.session_state.index = 0

def cargar_notebook(uploaded_file):
    nb = nbformat.read(uploaded_file, as_version=4)
    bloques = []
    for i, cell in enumerate(nb.cells, 1):
        tipo_celda = cell["cell_type"]
        contenido = cell["source"].strip()
        if not contenido:
            continue
        tipo = detectar_tipo_contenido(contenido)
        bloques.append((i, tipo_celda, tipo, contenido))
    st.session_state.bloques = bloques
    st.session_state.index = 0

if uploaded_file is not None and not st.session_state.bloques:
    cargar_notebook(uploaded_file)

# -------------------------
# Mostrar bloque actual
# -------------------------
def reproducir_bloque(i):
    if not st.session_state.bloques:
        return
    _, tipo_celda, tipo, contenido = st.session_state.bloques[i]
    st.subheader(f"📘 Bloque {i+1}")
    if tipo_celda == "markdown" and tipo == "texto":
        st.markdown(contenido)
        st.audio(text_to_speech(contenido), format="audio/mp3")
    elif tipo_celda == "markdown" and tipo in ["formula", "tabla"]:
        intro = describir_contenido(tipo, contenido)
        st.write(intro)
        st.audio(text_to_speech(intro), format="audio/mp3")
        st.markdown(contenido)
        st.audio(text_to_speech(contenido), format="audio/mp3")
    elif tipo_celda == "code":
        intro = describir_contenido("código", contenido)
        st.write(intro)
        st.audio(text_to_speech(intro), format="audio/mp3")
        st.code(contenido, language="python")

# -------------------------
# Botones grandes
# -------------------------
col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    if st.button("⬅️ Anterior", use_container_width=True):
        if st.session_state.index > 0:
            st.session_state.index -= 1
            st.rerun()

with col2:
    if st.button("⏯️ Reproducir / Pausar", use_container_width=True):
        reproducir_bloque(st.session_state.index)

with col3:
    if st.button("➡️ Siguiente", use_container_width=True):
        if st.session_state.index < len(st.session_state.bloques) - 1:
            st.session_state.index += 1
            st.rerun()

# Mostrar bloque actual
if st.session_state.bloques:
    reproducir_bloque(st.session_state.index)

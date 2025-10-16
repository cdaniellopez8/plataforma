import streamlit as st
import nbformat
from openai import OpenAI
from bs4 import BeautifulSoup
import requests
import re
import time

# Inicializar cliente de OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Lector Inclusivo", layout="wide")

st.title("🧠 Lector Inclusivo de Notebooks y RPubs")
st.write("""
Esta herramienta convierte documentos de Jupyter (`.ipynb`) o publicaciones de RPubs en una experiencia auditiva accesible.  
Usa los botones inferiores para navegar entre bloques de audio.
""")

# Estado de sesión para el control de bloques
if "bloques" not in st.session_state:
    st.session_state.bloques = []
    st.session_state.index = 0
    st.session_state.audios = []

# -------------------------
# Funciones base
# -------------------------
def detectar_tipo_contenido(texto):
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):  # fórmula LaTeX
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):  # tabla Markdown
        return "tabla"
    elif "```" in texto:
        return "codigo"
    else:
        return "texto"

def describir_contenido(tipo, texto):
    if tipo == "formula":
        prompt = f"""
        Eres un asistente para personas ciegas que lee notebooks.  
        Debes decir algo como:  
        "A continuación verás una fórmula. Esta trata sobre [explicación corta sin tecnicismos]."
        No recites símbolos.
        Contenido:
        {texto[:800]}
        """
    elif tipo == "tabla":
        prompt = f"""
        Eres un asistente para personas ciegas.  
        El contenido es una tabla.  
        Debes decir: "A continuación verás una tabla con las siguientes columnas:"  
        Luego describe las columnas con su tipo (numérica, texto, identificador, etc.)  
        Contenido:
        {texto[:1000]}
        """
    elif tipo == "codigo":
        prompt = f"""
        Eres un asistente para personas ciegas.  
        Describe brevemente qué hace el siguiente bloque de código sin leerlo línea por línea.
        Contenido:
        {texto[:1000]}
        """
    else:
        return texto  # texto normal
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return response.choices[0].message.content

def text_to_speech(text):
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return audio_response.read()

# -------------------------
# Procesamiento del notebook
# -------------------------
def procesar_notebook(file):
    nb = nbformat.read(file, as_version=4)
    bloques = []
    for cell in nb.cells:
        tipo = detectar_tipo_contenido(cell["source"])
        texto = cell["source"].strip()
        if not texto:
            continue
        bloques.append((tipo, texto))
    return bloques

# -------------------------
# Procesamiento de RPubs
# -------------------------
def procesar_rpubs(url):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        bloques = []
        for tag in soup.find_all(["p", "pre", "table", "h2", "h3", "h4"]):
            texto = tag.get_text(separator=" ", strip=True)
            if not texto:
                continue
            tipo = "texto"
            if tag.name == "pre":
                tipo = "codigo"
            elif tag.name == "table":
                tipo = "tabla"
            elif re.search(r"\\(|\\$.*\\$|\\[", texto):
                tipo = "formula"
            bloques.append((tipo, texto))
        return bloques
    except Exception as e:
        st.error(f"No se pudo procesar el enlace: {e}")
        return []

# -------------------------
# Entrada de usuario
# -------------------------
opcion = st.radio("Selecciona fuente de contenido:", ["Subir .ipynb", "Pegar enlace RPubs"])

if opcion == "Subir .ipynb":
    archivo = st.file_uploader("📤 Sube tu archivo .ipynb", type=["ipynb"])
    if archivo:
        st.session_state.bloques = procesar_notebook(archivo)
elif opcion == "Pegar enlace RPubs":
    enlace = st.text_input("🔗 Pega el enlace de RPubs")
    if enlace:
        st.session_state.bloques = procesar_rpubs(enlace)

# -------------------------
# Generar audios al cargar
# -------------------------
if st.session_state.bloques and not st.session_state.audios:
    with st.spinner("🎧 Preparando audios..."):
        for tipo, texto in st.session_state.bloques:
            descripcion = describir_contenido(tipo, texto)
            audio_bytes = text_to_speech(descripcion)
            st.session_state.audios.append((descripcion, audio_bytes))
        st.success("✅ Audios listos para reproducir.")

# -------------------------
# Controles de navegación
# -------------------------
if st.session_state.audios:
    index = st.session_state.index
    total = len(st.session_state.audios)
    descripcion, audio = st.session_state.audios[index]

    st.markdown(f"### 🔊 Bloque {index + 1} de {total}")
    st.write(descripcion)
    st.audio(audio, format="audio/mp3")

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("⬅️ Anterior", use_container_width=True):
            if st.session_state.index > 0:
                st.session_state.index -= 1
                st.experimental_rerun()

    with col2:
        if st.button("⏸️ Pausa / Reproducir", use_container_width=True):
            st.info("Usa el control del reproductor para pausar o reanudar el audio.")

    with col3:
        if st.button("➡️ Siguiente", use_container_width=True):
            if st.session_state.index < total - 1:
                st.session_state.index += 1
                st.experimental_rerun()



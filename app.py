import streamlit as st
import nbformat
from openai import OpenAI
import re
import base64
import time

# Inicializar cliente OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")
st.write("""
Esta aplicación convierte notebooks de Jupyter en una experiencia auditiva accesible.

🧭 **Instrucciones:**
- Sube un archivo `.ipynb`.
- Escucha la lectura de cada bloque.
- Usa el **botón grande central**:
  - 👆 *Un clic:* pausa o reanuda el audio actual.  
  - 👆👆 *Doble clic:* pasa al siguiente bloque.  
- Los botones de **reiniciar** y **anterior** están debajo.
""")

uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

# --- Detección del tipo de contenido ---
def detectar_tipo_contenido(texto):
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):
        return "tabla"
    else:
        return "texto"

# --- Descripción guiada según tipo ---
def describir_contenido(tipo, texto):
    if tipo == "formula":
        prompt = f"""
        Eres un asistente que apoya a personas ciegas leyendo notebooks.
        Vas a generar una frase en español:
        "A continuación verás una fórmula. Esta trata sobre [explicación corta del tema de la fórmula, sin símbolos]."
        No leas los signos matemáticos ni digas 'símbolos extraños'.
        Contenido:
        {texto[:800]}
        """
    elif tipo == "tabla":
        prompt = f"""
        Eres un asistente que apoya a personas ciegas leyendo notebooks.
        El contenido es una tabla.
        Primero di: "A continuación verás una tabla con las siguientes columnas:"
        Luego menciona cada columna junto con su tipo de dato inferido (numérica, texto, fecha, etc.)
        Contenido:
        {texto[:1000]}
        """
    else:
        return texto

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content

# --- Conversión texto a voz ---
def text_to_speech(text):
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return audio_response.read()

# --- Inicialización de sesión ---
if "audios" not in st.session_state:
    st.session_state.audios = []
if "index" not in st.session_state:
    st.session_state.index = 0
if "audio_urls" not in st.session_state:
    st.session_state.audio_urls = []
if "is_playing" not in st.session_state:
    st.session_state.is_playing = False
if "hover_played" not in st.session_state:
    st.session_state.hover_played = False

# --- Procesamiento del archivo ---
if uploaded_file:
    notebook = nbformat.read(uploaded_file, as_version=4)
    audios = []

    for cell in notebook.cells:
        if not cell["source"].strip():
            continue

        cell_type = cell["cell_type"]
        texto = cell["source"].strip()
        tipo = detectar_tipo_contenido(texto)

        if cell_type == "markdown" and tipo in ["formula", "tabla"]:
            explicacion = describir_contenido(tipo, texto)
            combined_text = f"{explicacion}. {texto}"
        else:
            combined_text = texto

        audios.append(combined_text)

    st.session_state.audios = audios

# --- Reproducir audio ---
def reproducir_audio(idx):
    texto = st.session_state.audios[idx]
    audio_bytes = text_to_speech(texto)
    audio_base64 = base64.b64encode(audio_bytes).decode()
    audio_html = f"""
    <audio id="audio_player" autoplay>
        <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
    </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

# --- Botones grandes ---
if st.session_state.audios:
    idx = st.session_state.index
    st.markdown(f"### 🔊 Bloque {idx + 1} de {len(st.session_state.audios)}")
    st.text_area("Contenido del bloque:", st.session_state.audios[idx], height=150)

    # JS para hover y control de clics
    js_script = """
    <script>
    let audio = document.getElementById("audio_player");
    let button = document.getElementById("mainButton");
    let lastClick = 0;

    button.onmouseenter = () => {
        if (!window.hasPlayedHover) {
            const hoverAudio = new Audio('data:audio/mp3;base64,{{hover_audio}}');
            hoverAudio.play();
            window.hasPlayedHover = true;
        }
    };

    button.onclick = () => {
        const now = Date.now();
        if (now - lastClick < 400) {
            window.parent.postMessage({ type: "next" }, "*");
        } else {
            if (audio.paused) audio.play();
            else audio.pause();
        }
        lastClick = now;
    };
    </script>
    """

    # Generar audio del hover (una sola vez)
    hover_audio = text_to_speech("Botón principal. Un clic pausa o reanuda. Doble clic pasa al siguiente bloque.")
    hover_b64 = base64.b64encode(hover_audio).decode()

    # Reproducir bloque actual
    reproducir_audio(idx)

    # Renderizar botones
    st.markdown(f"""
    <div style="text-align:center; margin-top: 30px;">
        <button id="mainButton" style="width:300px; height:100px; font-size:24px; background-color:#007bff; color:white; border-radius:12px;">
            🎧 Control principal
        </button>
        <div style="margin-top:20px;">
            <button id="restart" style="width:200px; height:70px; font-size:20px; background-color:#f39c12; color:white; border-radius:10px;">🔄 Reiniciar</button>
            <button id="prev" style="width:200px; height:70px; font-size:20px; background-color:#27ae60; color:white; border-radius:10px;">⬅️ Anterior</button>
        </div>
    </div>
    """ + js_script.replace("{{hover_audio}}", hover_b64), unsafe_allow_html=True)

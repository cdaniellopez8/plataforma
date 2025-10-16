import streamlit as st
import nbformat
from openai import OpenAI
import re
import time

# Inicializar cliente
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")

# Instrucciones iniciales habladas
instrucciones_texto = """
Bienvenido al lector inclusivo de notebooks.
Esta aplicación leerá en voz alta el contenido de tu archivo paso a paso.
Solo hay un botón grande en pantalla.
Presiona una vez para pausar o reanudar el audio actual.
Presiona dos veces seguidas para pasar al siguiente bloque automáticamente.
"""

# Convertir instrucciones a audio
def text_to_speech(text):
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return audio_response.read()

# Mostrar instrucciones y reproducir
st.write(instrucciones_texto)
st.audio(text_to_speech(instrucciones_texto), format="audio/mp3")

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
        Explica brevemente en español, con lenguaje natural, qué trata esta fórmula.
        No leas símbolos ni ecuaciones. Usa frases como:
        "A continuación verás una fórmula que explica..."
        Contenido:
        {texto[:800]}
        """
    elif tipo == "tabla":
        prompt = f"""
        Eres un asistente que apoya a personas ciegas leyendo notebooks.
        Describe brevemente la tabla.
        Di: "A continuación verás una tabla con las siguientes columnas:"
        Luego menciona las columnas y sus tipos de dato (numérico, texto, fecha, etc.).
        Contenido:
        {texto[:1000]}
        """
    elif tipo == "código":
        prompt = f"""
        Eres un asistente que ayuda a personas ciegas a entender código Python.
        Explica brevemente qué hace el código, en español, sin leerlo literalmente.
        Contenido:
        {texto[:1000]}
        """
    else:
        return texto

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return response.choices[0].message.content

# -------------------------
# Reproductor interactivo
# -------------------------
if uploaded_file is not None:
    notebook = nbformat.read(uploaded_file, as_version=4)
    cells = [cell for cell in notebook.cells if cell["source"].strip()]
    total = len(cells)

    if "indice" not in st.session_state:
        st.session_state.indice = 0
        st.session_state.paused = False
        st.session_state.last_click = 0.0

    i = st.session_state.indice
    cell = cells[i]
    tipo = detectar_tipo_contenido(cell["source"])

    # Obtener texto y explicación
    if cell["cell_type"] == "code":
        explicacion = describir_contenido("código", cell["source"])
    elif tipo in ["formula", "tabla"]:
        explicacion = describir_contenido(tipo, cell["source"])
    else:
        explicacion = cell["source"]

    # Mostrar contenido textual y audio
    st.markdown(f"### 🔊 Bloque {i+1} de {total}")
    st.markdown(explicacion)
    st.audio(text_to_speech(explicacion), format="audio/mp3")

    # Botón grande único
    st.markdown(
        """
        <style>
        div.stButton > button {
            width: 100%;
            height: 120px;
            font-size: 28px;
            background-color: #4682B4;
            color: white;
            border-radius: 15px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Acción del botón
    if st.button("🎵 Reproducir / Pausar / Siguiente"):
        now = time.time()
        if now - st.session_state.last_click < 0.6:
            # Doble clic → siguiente bloque
            st.session_state.indice += 1
            if st.session_state.indice >= total:
                st.success("✅ Has terminado de escuchar el notebook completo.")
            st.rerun()
        else:
            # Un solo clic → alternar pausa
            st.session_state.paused = not st.session_state.paused
            st.info("⏸️ Pausa activada" if st.session_state.paused else "▶️ Reproduciendo")
        st.session_state.last_click = now

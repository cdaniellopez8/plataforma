import streamlit as st
import nbformat
from openai import OpenAI
import base64

# Inicializar cliente
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🎧 Lector Interactivo de Notebooks (.ipynb)")
st.write("Sube un archivo `.ipynb` y el sistema explicará cada bloque y lo leerá en voz alta.")

# Subir archivo
uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

# ---- Función para describir cada celda ----
def describe_chunk(cell_type, cell_source):
    prompt = f"""
    Resume de forma breve y accesible lo que se hace o muestra en el siguiente bloque de un notebook Jupyter.
    Indica si es texto, código o una tabla, y explica lo esencial que vendrá.
    ---
    Tipo de celda: {cell_type}
    Contenido:
    {cell_source[:1000]}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content

# ---- Función para convertir texto a audio ----
def text_to_speech(text):
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    audio_bytes = audio_response.read()
    return audio_bytes

# ---- Procesamiento del archivo ----
if uploaded_file is not None:
    notebook = nbformat.read(uploaded_file, as_version=4)

    for i, cell in enumerate(notebook.cells, 1):
        cell_type = cell["cell_type"]
        cell_source = cell["source"]

        with st.spinner(f"🔎 Analizando bloque {i}..."):
            description = describe_chunk(cell_type, cell_source)

        # Mostrar descripción
        st.markdown(f"### 💡 Bloque {i}: descripción")
        st.write(description)

        # Reproducir audio
        try:
            audio_bytes = text_to_speech(description)
            st.audio(audio_bytes, format="audio/mp3")
        except Exception as e:
            st.error(f"No se pudo generar el audio: {e}")

        # Mostrar el contenido del bloque
        if cell_type == "markdown":
            st.markdown(cell_source)
        elif cell_type == "code":
            st.code(cell_source, language="python")


import streamlit as st
import nbformat
from openai import OpenAI
import re

# Inicializar cliente
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🧠 Lector Inteligente e Inclusivo de Notebooks (.ipynb)")
st.write("""
Sube un archivo `.ipynb` y el sistema leerá su contenido en voz alta.  
- Si es **texto**, lo leerá directamente.  
- Si es **una fórmula o una tabla**, primero la **explicará brevemente** y luego la **recitará**.
""")

uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

# -------------------------
# Función para identificar el tipo de contenido
# -------------------------
def detectar_tipo_contenido(texto):
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):  # detección de fórmula LaTeX
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):  # markdown table o formato tabular
        return "tabla"
    else:
        return "texto"

# -------------------------
# Descripción sencilla antes de fórmulas o tablas
# -------------------------
def describir_contenido(tipo, texto):
    prompt = f"""
    Eres un asistente que ayuda a personas ciegas a entender notebooks.  
    Si el contenido es una fórmula o tabla, descríbelo brevemente de forma sencilla y luego recítalo.  
    Evita tecnicismos. No hables en plural ni repitas el texto.
    ---
    Tipo: {tipo}
    Contenido:
    {texto[:1000]}
    """
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
# Procesar archivo
# -------------------------
if uploaded_file is not None:
    notebook = nbformat.read(uploaded_file, as_version=4)

    for i, cell in enumerate(notebook.cells, 1):
        cell_type = cell["cell_type"]
        cell_source = cell["source"].strip()

        if not cell_source:
            continue

        with st.spinner(f"🪶 Procesando bloque {i}..."):
            tipo = detectar_tipo_contenido(cell_source)

            if cell_type == "markdown":
                if tipo == "texto":
                    # Leer directamente el texto
                    st.markdown(cell_source)
                    audio_bytes = text_to_speech(cell_source)
                    st.audio(audio_bytes, format="audio/mp3")

                else:
                    # Explicar primero si es fórmula o tabla
                    explicacion = describir_contenido(tipo, cell_source)
                    st.markdown(f"### 💬 Descripción del bloque {i}")
                    st.write(explicacion)
                    st.audio(text_to_speech(explicacion), format="audio/mp3")

                    st.markdown(cell_source)
                    st.audio(text_to_speech(cell_source), format="audio/mp3")

            elif cell_type == "code":
                # Describir código como antes
                explicacion = describir_contenido("código", cell_source)
                st.markdown(f"### 💡 Bloque de código {i}")
                st.write(explicacion)
                st.audio(text_to_speech(explicacion), format="audio/mp3")
                st.code(cell_source, language="python")



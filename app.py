import streamlit as st
import json
from gtts import gTTS
import io
import openai

openai.api_key = st.secrets["OPENAI_API_KEY"]

def describe_chunk(cell_type, text):
    """Genera una descripción breve con ayuda de un LLM."""
    prompt = f"""
    Eres un asistente de accesibilidad para personas ciegas.
    Resume brevemente lo que contiene la siguiente celda de un notebook de Python.
    Si es código, explica qué hace; si es texto, indica de qué trata;
    si es una tabla o gráfico, descríbelo de manera general.
    Celda tipo: {cell_type}
    Contenido:
    {text[:2000]}
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


def tts_from_text(text, lang="es"):
    """Convierte texto a audio en memoria."""
    tts = gTTS(text, lang=lang)
    audio_bytes = io.BytesIO()
    tts.write_to_fp(audio_bytes)
    return audio_bytes.getvalue()


st.title("🎧 Lector accesible de Notebooks (.ipynb)")

uploaded_file = st.file_uploader("Sube tu archivo .ipynb", type=["ipynb"])

if uploaded_file is not None:
    notebook = json.load(uploaded_file)
    st.success("Archivo cargado correctamente ✅")

    cells = notebook.get("cells", [])
    st.write(f"Se encontraron **{len(cells)}** celdas en el notebook.")

    for i, cell in enumerate(cells):
        cell_type = cell.get("cell_type", "")
        cell_source = "".join(cell.get("source", [])).strip()

        if not cell_source:
            continue

        st.markdown(f"### 📦 Celda {i+1} ({cell_type})")

        if st.button(f"🔊 Escuchar celda {i+1}", key=f"btn{i}"):
            # LLM genera la descripción previa
            description = describe_chunk(cell_type, cell_source)
            full_text = f"{description}. Ahora el contenido: {cell_source}"

            # Convertir a audio
            audio = tts_from_text(full_text)
            st.audio(audio, format="audio/mp3")

        # Mostrar vista previa textual
        st.code(cell_source[:500] + ("..." if len(cell_source) > 500 else ""), language="python" if cell_type=="code" else None)
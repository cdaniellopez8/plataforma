import streamlit as st
import json
from gtts import gTTS
import io
from openai import OpenAI


client = OpenAI()

openai.api_key = st.secrets["OPENAI_API_KEY"]

def describe_chunk(cell_type, cell_source):
    prompt = f"""
    Resume brevemente qué se hace o se muestra en el siguiente bloque de un notebook Jupyter.
    Indica si es texto, código o una tabla y describe lo esencial de lo que viene.
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

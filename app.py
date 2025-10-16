import streamlit as st
import nbformat
from openai import OpenAI

# Inicializar cliente de OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("📘 Lector Inteligente de Notebooks Jupyter (.ipynb)")
st.write("Sube un archivo `.ipynb` y el modelo te explicará cada celda antes de mostrarla.")

# Subir archivo
uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

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

if uploaded_file is not None:
    # Leer el archivo .ipynb
    notebook = nbformat.read(uploaded_file, as_version=4)
    
    for cell in notebook.cells:
        cell_type = cell["cell_type"]
        cell_source = cell["source"]

        # Pedir descripción con LLM
        with st.spinner("Analizando bloque..."):
            description = describe_chunk(cell_type, cell_source)
        
        st.markdown(f"### 💡 Descripción del siguiente bloque:")
        st.write(description)

        # Mostrar contenido del bloque
        if cell_type == "markdown":
            st.markdown(cell_source)
        elif cell_type == "code":
            st.code(cell_source, language="python")


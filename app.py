import streamlit as st
import nbformat
from openai import OpenAI
import re
import io

# -------------------------
# Configuración inicial
# -------------------------
st.set_page_config(page_title="Lector Inclusivo de Notebooks", layout="centered")
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")

# Instrucciones habladas y visibles
instrucciones = """
Bienvenido al lector inclusivo. 
Esta aplicación convierte notebooks de Jupyter en una experiencia auditiva accesible.

1. Sube un archivo con extensión `.ipynb`.
2. Usa los botones para moverte entre bloques:
   - 'Anterior bloque' para retroceder.
   - 'Reproducir / Pausar' para escuchar el bloque actual.
   - 'Siguiente bloque' para avanzar.
3. Si el bloque contiene una **fórmula o tabla**, primero escucharás una descripción sencilla antes de leer el contenido.
"""
st.markdown(instrucciones)

# -------------------------
# Funciones
# -------------------------
def detectar_tipo_contenido(texto):
    """Detecta si el contenido es texto, fórmula o tabla."""
    texto = texto.strip()
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):
        return "tabla"
    else:
        return "texto"

def limpiar_texto(texto):
    """Elimina encabezados (#) y espacios innecesarios."""
    lineas = texto.split("\n")
    lineas_limpias = [l for l in lineas if not l.strip().startswith("#")]
    return "\n".join(lineas_limpias).strip()

def describir_contenido(tipo, texto):
    """Genera una breve descripción hablada del bloque."""
    if tipo == "formula":
        prompt = f"""
        Eres un asistente que apoya a personas ciegas leyendo notebooks.  
        Vas a generar una frase introductoria breve con este formato:
        "A continuación verás una fórmula. Esta trata sobre [una breve descripción general sin símbolos ni fórmulas]."
        Contenido:
        {texto[:800]}
        """
    elif tipo == "tabla":
        prompt = f"""
        Eres un asistente que apoya a personas ciegas leyendo notebooks.  
        El contenido es una tabla.  
        Primero di: "A continuación verás una tabla con las siguientes columnas:"  
        Luego, menciona cada columna junto con su tipo de dato inferido (numérica, texto, identificador, fecha, etc.).  
        Contenido:
        {texto[:1000]}
        """
    else:
        return texto  # texto plano no necesita descripción

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return response.choices[0].message.content.strip()

def text_to_speech(text):
    """Convierte texto a audio."""
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return io.BytesIO(audio_response.read())

# -------------------------
# Subida del archivo
# -------------------------
uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

if uploaded_file:
    notebook = nbformat.read(uploaded_file, as_version=4)
    bloques = []

    # Procesar cada celda
    for cell in notebook.cells:
        if cell["cell_type"] == "markdown":
            texto = limpiar_texto(cell["source"])
            if texto:
                tipo = detectar_tipo_contenido(texto)
                bloques.append((tipo, texto))
        elif cell["cell_type"] == "code":
            texto = cell["source"].strip()
            if texto:
                bloques.append(("codigo", texto))

    # Si es un nuevo archivo, reiniciar el índice
    if "ultimo_archivo" not in st.session_state or st.session_state.ultimo_archivo != uploaded_file.name:
        st.session_state.index = 0
        st.session_state.ultimo_archivo = uploaded_file.name

    # Control de navegación
    def siguiente():
        if st.session_state.index < len(bloques) - 1:
            st.session_state.index += 1

    def anterior():
        if st.session_state.index > 0:
            st.session_state.index -= 1

    tipo, texto = bloques[st.session_state.index]
    texto = limpiar_texto(texto)

    st.markdown(f"### 📘 Bloque {st.session_state.index + 1} de {len(bloques)}")

    # Mostrar descripción y audio según tipo
    if tipo in ["formula", "tabla"]:
        descripcion = describir_contenido(tipo, texto)
        st.write(descripcion)
        st.audio(text_to_speech(descripcion), format="audio/mp3")
        st.audio(text_to_speech(texto), format="audio/mp3")
    elif tipo == "codigo":
        st.write("A continuación verás un bloque de código.")
        st.code(texto, language="python")
        st.audio(text_to_speech("A continuación verás un bloque de código."), format="audio/mp3")
    else:
        st.audio(text_to_speech(texto), format="audio/mp3")

    # -------------------------
    # Botones de control
    # -------------------------
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("⏮️ Anterior", on_click=anterior, use_container_width=True)
    with col2:
        st.button("⏭️ Siguiente", on_click=siguiente, use_container_width=True)
    with col3:
        st.download_button("🔊 Descargar audio actual", text_to_speech(texto), file_name=f"bloque_{st.session_state.index+1}.mp3")


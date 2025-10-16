import streamlit as st
import nbformat
import requests
import openai
import tempfile
import PyPDF2
from io import BytesIO
from gtts import gTTS

# Configurar clave
from openai import OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Lectura Accesible de RPubs", layout="centered")

st.title("📖 Plataforma Accesible para Lectura de RPubs o Notebooks")

st.markdown("""
Sube un archivo `.ipynb` **o** pega un enlace de **RPubs**.  
El sistema generará fragmentos de audio con descripciones accesibles para cada bloque.
""")

# =====================
# Funciones auxiliares
# =====================

def describir_chunk(tipo, contenido):
    """Genera una breve descripción solo si es una tabla o fórmula"""
    if tipo == "code":
        if "plot" in contenido.lower() or "ggplot" in contenido.lower():
            prompt = "Describe en lenguaje simple qué muestra el gráfico generado por este código en R."
        elif "<-" in contenido or "=" in contenido:
            prompt = "Explica brevemente de qué trata esta fórmula o cálculo sin entrar en detalles matemáticos."
        else:
            prompt = None
    elif tipo == "markdown":
        prompt = None
    else:
        prompt = None

    if not prompt:
        return None

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt + "\n\n" + contenido}]
    )

    return response.choices[0].message.content.strip()


def texto_a_audio(texto):
    """Convierte texto a audio temporal"""
    tts = gTTS(text=texto, lang="es")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tts.save(tmp.name)
        return tmp.name


def leer_pdf(pdf_bytes):
    """Extrae texto de un PDF"""
    reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text


def obtener_texto_de_rpubs(url):
    """Descarga el HTML de un RPubs"""
    response = requests.get(url)
    response.raise_for_status()
    text = response.text
    # Extraer texto del HTML (básico)
    clean_text = ' '.join(text.split())
    return clean_text


# =====================
# Entrada del usuario
# =====================

uploaded_file = st.file_uploader("Sube un archivo .ipynb o .pdf", type=["ipynb", "pdf"])
rpubs_link = st.text_input("O pega un enlace de RPubs:")

chunks = []

if uploaded_file:
    if uploaded_file.name.endswith(".ipynb"):
        nb = nbformat.read(uploaded_file, as_version=4)
        for cell in nb.cells:
            contenido = cell["source"]
            tipo = cell["cell_type"]
            desc = describir_chunk(tipo, contenido)
            texto_final = f"A continuación verás una fórmula: {desc}\n\n{contenido}" if desc else contenido
            chunks.append(texto_final)
    elif uploaded_file.name.endswith(".pdf"):
        pdf_text = leer_pdf(uploaded_file.read())
        chunks = pdf_text.split("\n\n")
elif rpubs_link:
    try:
        texto_rpubs = obtener_texto_de_rpubs(rpubs_link)
        chunks = texto_rpubs.split(". ")
    except Exception as e:
        st.error(f"No se pudo procesar el enlace: {e}")

# =====================
# Reproductor accesible
# =====================

if chunks:
    # Reiniciar índice si cambia el contenido
    if "ultimo_total" not in st.session_state or st.session_state["ultimo_total"] != len(chunks):
        st.session_state["indice"] = 0
        st.session_state["ultimo_total"] = len(chunks)

    idx = st.session_state["indice"]

    # Controlar que el índice no se salga del rango
    if idx < 0:
        st.session_state["indice"] = 0
        idx = 0
    elif idx >= len(chunks):
        st.session_state["indice"] = len(chunks) - 1
        idx = len(chunks) - 1

    st.markdown(f"### 🔹 Fragmento {idx + 1} de {len(chunks)}")

    # Mostrar texto actual
    texto_actual = chunks[idx] if len(chunks) > 0 else "(sin texto)"
    st.text_area("Texto actual:", texto_actual, height=200)

    # Generar audio
    audio_path = texto_a_audio(texto_actual)
    st.audio(audio_path)

    # Controles accesibles
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("⬅️ Anterior"):
            if st.session_state["indice"] > 0:
                st.session_state["indice"] -= 1
                st.rerun()
    with col2:
        st.button("⏸️ Pausar / Reanudar")  # placeholder visual
    with col3:
        if st.button("➡️ Siguiente"):
            if st.session_state["indice"] < len(chunks) - 1:
                st.session_state["indice"] += 1
                st.rerun()



import streamlit as st
import nbformat
from openai import OpenAI
import re
import base64

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Lector Inclusivo", layout="centered")
st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")

# -------------------------
# Función para generar audio
# -------------------------
def text_to_speech(text):
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return audio_response.read()

# -------------------------
# Instrucciones iniciales
# -------------------------
instrucciones = """
Bienvenido al lector inclusivo de notebooks.
Esta aplicación leerá el contenido de tu archivo paso a paso.
Solo hay un botón grande en pantalla:
- Un clic: pausa o reanuda el audio.
- Doble clic: pasa al siguiente bloque automáticamente.
Cuando pases el cursor por encima del botón, escucharás una guía auditiva.
"""
audio_instrucciones = text_to_speech(instrucciones)

st.markdown("### 🧭 Instrucciones")
st.write(instrucciones)

# Mostrar audio inicial
audio_b64 = base64.b64encode(audio_instrucciones).decode()
st.markdown(
    f"""
    <audio id="instruccionesAudio" autoplay>
      <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
    </audio>
    """,
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader("📤 Sube tu archivo .ipynb", type=["ipynb"])

# -------------------------
# Detectar tipo de contenido
# -------------------------
def detectar_tipo_contenido(texto):
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):
        return "tabla"
    else:
        return "texto"

# -------------------------
# Descripción accesible
# -------------------------
def describir_contenido(tipo, texto):
    if tipo == "formula":
        prompt = f"""
        Explica brevemente en español, con lenguaje natural, qué trata esta fórmula.
        No leas símbolos ni ecuaciones. Usa frases como:
        "A continuación verás una fórmula que explica..."
        Contenido:
        {texto[:800]}
        """
    elif tipo == "tabla":
        prompt = f"""
        Describe brevemente la tabla en español.
        Di: "A continuación verás una tabla con las siguientes columnas:"
        Luego menciona las columnas y sus tipos de dato.
        Contenido:
        {texto[:1000]}
        """
    elif tipo == "código":
        prompt = f"""
        Explica brevemente qué hace este código Python, en español, sin leerlo literalmente.
        Contenido:
        {texto[:1000]}
        """
    else:
        return texto

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    return response.choices[0].message.content

# -------------------------
# Reproducción del contenido
# -------------------------
if uploaded_file is not None:
    notebook = nbformat.read(uploaded_file, as_version=4)
    cells = [c for c in notebook.cells if c["source"].strip()]
    total = len(cells)

    if "indice" not in st.session_state:
        st.session_state.indice = 0

    i = st.session_state.indice
    cell = cells[i]
    tipo = detectar_tipo_contenido(cell["source"])

    if cell["cell_type"] == "code":
        texto = describir_contenido("código", cell["source"])
    elif tipo in ["formula", "tabla"]:
        texto = describir_contenido(tipo, cell["source"])
    else:
        texto = cell["source"]

    audio_data = text_to_speech(texto)
    audio_b64 = base64.b64encode(audio_data).decode()

    st.markdown(f"### 🔊 Bloque {i+1} de {total}")
    st.markdown(texto)

    # Reproductor de audio controlable desde JS
    st.markdown(
        f"""
        <audio id="lectorAudio" autoplay>
          <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
        </audio>

        <audio id="hoverAudio">
          <source src="data:audio/mp3;base64,{base64.b64encode(text_to_speech('Botón de reproducción. Haz un clic para pausar o dos clics para pasar al siguiente bloque.')).decode()}" type="audio/mp3">
        </audio>

        <style>
        #lectorBtn {{
            width: 100%;
            height: 120px;
            font-size: 30px;
            background-color: #4682B4;
            color: white;
            border: none;
            border-radius: 18px;
            cursor: pointer;
        }}
        #lectorBtn:hover {{
            background-color: #5A9BD3;
        }}
        </style>

        <button id="lectorBtn">🎵 Reproducir / Pausar / Siguiente</button>

        <script>
        const btn = document.getElementById('lectorBtn');
        const audio = document.getElementById('lectorAudio');
        const hoverAudio = document.getElementById('hoverAudio');
        let lastClick = 0;

        btn.addEventListener('mouseenter', () => {{
            hoverAudio.currentTime = 0;
            hoverAudio.play();
        }});

        btn.addEventListener('click', () => {{
            const now = Date.now();
            if (now - lastClick < 500) {{
                // Doble clic → siguiente bloque
                window.parent.postMessage({{ type: 'streamlit:rerun' }}, '*');
            }} else {{
                // Clic simple → pausa o reanuda
                if (audio.paused) {{
                    audio.play();
                }} else {{
                    audio.pause();
                }}
            }}
            lastClick = now;
        }});
        </script>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.indice >= total:
        st.success("✅ Has terminado de escuchar el notebook completo.")

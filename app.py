import streamlit as st
import nbformat
from gtts import gTTS
import base64
import io
import re

st.set_page_config(page_title="Lector Inclusivo de Notebook", layout="centered")

# --- Función para convertir texto a audio (mp3 en base64) ---
def text_to_audio_base64(text, lang="es"):
    tts = gTTS(text=text, lang=lang)
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

# --- Limpieza de texto (evita leer títulos y símbolos) ---
def limpiar_texto(texto):
    texto = re.sub(r"#+", "", texto)  # eliminar #
    texto = re.sub(r"[\*\_\~\`\>\-]", "", texto)  # limpiar markdown
    texto = texto.strip()
    return texto

# --- Descripción automática del tipo de contenido ---
def describir_para_usuario(tipo, texto):
    texto = limpiar_texto(texto)
    if tipo == "code":
        return "A continuación verás una celda de código, que contiene instrucciones en lenguaje Python."
    elif tipo == "markdown":
        return "A continuación escucharás una descripción de texto explicativo."
    elif tipo == "output":
        return "A continuación escucharás el resultado de una celda ejecutada."
    else:
        return "Contenido no identificado."

# --- Procesar notebook ---
def procesar_notebook(archivo):
    nb = nbformat.read(archivo, as_version=4)
    chunks = []
    for cell in nb.cells:
        tipo = cell.cell_type
        texto = str(cell.source)
        if not texto.strip():
            continue
        descripcion = describir_para_usuario(tipo, texto)
        contenido = limpiar_texto(texto[:1000])
        chunks.append(f"{descripcion} {contenido}")
    return chunks

# --- Inicialización de variables de sesión ---
if "chunks" not in st.session_state:
    st.session_state.chunks = []
if "index" not in st.session_state:
    st.session_state.index = 0
if "audio_uris" not in st.session_state:
    st.session_state.audio_uris = []

# --- Subida de archivo ---
st.title("🧠 Lector inclusivo de notebooks (.ipynb)")
archivo = st.file_uploader("Por favor, carga tu archivo .ipynb", type=["ipynb"])

# --- Procesamiento del archivo ---
if archivo:
    if not st.session_state.chunks:
        st.session_state.chunks = procesar_notebook(archivo)
        st.session_state.audio_uris = [None] * len(st.session_state.chunks)
        st.session_state.index = 0

    def ensure_audio_for_index(i):
        if st.session_state.audio_uris[i] is None:
            texto = st.session_state.chunks[i]
            audio_b64 = text_to_audio_base64(texto)
            st.session_state.audio_uris[i] = f"data:audio/mp3;base64,{audio_b64}"

    def reproducir_audio(i):
        ensure_audio_for_index(i)
        audio_html = f"""
        <audio id="audio" autoplay controls>
            <source src="{st.session_state.audio_uris[i]}" type="audio/mp3">
        </audio>
        """
        st.markdown(audio_html, unsafe_allow_html=True)

    current_idx = st.session_state.index
    total = len(st.session_state.chunks)

    st.markdown(f"### Fragmento {current_idx + 1} de {total}")
    st.text_area("Texto actual:", st.session_state.chunks[current_idx], height=200)

    # --- Reproduce automáticamente al cargar ---
    reproducir_audio(current_idx)

    # --- Controles accesibles ---
    col1, col2, col3 = st.columns(3)

    # Botón anterior
    with col1:
        if st.button("⏮️ Anterior", use_container_width=True):
            if st.session_state.index > 0:
                st.session_state.index -= 1
                st.rerun()
        st.markdown(
            """
            <audio id="hoverPrev" src="data:audio/mp3;base64,{}"></audio>
            <script>
            const prevButton = window.parent.document.querySelector('button[kind="secondary"]');
            prevButton.addEventListener('mouseenter', ()=>{{document.getElementById('hoverPrev').play();}});
            </script>
            """.format(text_to_audio_base64("Botón anterior")), unsafe_allow_html=True
        )

    # Botón reproducir/pausar
    with col2:
        if st.button("⏯️ Reproducir/Pausar", use_container_width=True):
            st.markdown(
                """
                <script>
                var audio = document.getElementById('audio');
                if (audio.paused) { audio.play(); } else { audio.pause(); }
                </script>
                """,
                unsafe_allow_html=True,
            )
        st.markdown(
            """
            <audio id="hoverPlay" src="data:audio/mp3;base64,{}"></audio>
            <script>
            const playButton = window.parent.document.querySelectorAll('button[kind="secondary"]')[1];
            playButton.addEventListener('mouseenter', ()=>{{document.getElementById('hoverPlay').play();}});
            </script>
            """.format(text_to_audio_base64("Botón reproducir o pausar")), unsafe_allow_html=True
        )

    # Botón siguiente
    with col3:
        if st.button("⏭️ Siguiente", use_container_width=True):
            if st.session_state.index < total - 1:
                st.session_state.index += 1
                st.rerun()
        st.markdown(
            """
            <audio id="hoverNext" src="data:audio/mp3;base64,{}"></audio>
            <script>
            const nextButton = window.parent.document.querySelectorAll('button[kind="secondary"]')[2];
            nextButton.addEventListener('mouseenter', ()=>{{document.getElementById('hoverNext').play();}});
            </script>
            """.format(text_to_audio_base64("Botón siguiente")), unsafe_allow_html=True
        )

else:
    st.info("Por favor, sube un archivo .ipynb para comenzar.")
    st.markdown("📢 Este lector te guiará con audio paso a paso una vez cargues el archivo.")

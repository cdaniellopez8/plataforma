import streamlit as st
import nbformat
from gtts import gTTS
import base64
import io
import re

st.set_page_config(page_title="Lector Inclusivo de Notebook", layout="centered")

# --- Función para convertir texto a audio (mp3 en base64) ---
def text_to_audio_base64(text, lang="es-us"):  # Español latino
    tts = gTTS(text=text, lang=lang, tld="com.mx")  # Acento mexicano
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

    current_idx = st.session_state.index
    total = len(st.session_state.chunks)

    st.markdown(f"### Fragmento {current_idx + 1} de {total}")
    st.text_area("Texto actual:", st.session_state.chunks[current_idx], height=200)

    # --- Genera audio para el fragmento actual ---
    ensure_audio_for_index(current_idx)
    
    # --- Reproduce el audio principal ---
    audio_html = f"""
    <audio id="audioMain" autoplay controls style="width: 100%;">
        <source src="{st.session_state.audio_uris[current_idx]}" type="audio/mp3">
    </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

    # --- Audios hover para los botones ---
    audio_prev_b64 = text_to_audio_base64("Anterior")
    audio_play_b64 = text_to_audio_base64("Reproducir o pausar")
    audio_next_b64 = text_to_audio_base64("Siguiente")

    # Insertar audios ocultos para hover
    st.markdown(f"""
    <audio id="hoverPrev" src="data:audio/mp3;base64,{audio_prev_b64}"></audio>
    <audio id="hoverPlay" src="data:audio/mp3;base64,{audio_play_b64}"></audio>
    <audio id="hoverNext" src="data:audio/mp3;base64,{audio_next_b64}"></audio>
    """, unsafe_allow_html=True)

    # --- Controles accesibles ---
    col1, col2, col3 = st.columns(3)

    # Botón anterior
    with col1:
        if st.button("⏮️ Anterior", use_container_width=True, key="btn_prev"):
            if st.session_state.index > 0:
                st.session_state.index -= 1
                st.rerun()

    # Botón reproducir/pausar
    with col2:
        st.button("⏯️ Reproducir/Pausar", use_container_width=True, key="btn_play")

    # Botón siguiente
    with col3:
        if st.button("⏭️ Siguiente", use_container_width=True, key="btn_next"):
            if st.session_state.index < total - 1:
                st.session_state.index += 1
                st.rerun()

    # --- JavaScript para controlar audio y hover ---
    st.markdown("""
    <script>
    // Esperar a que el DOM esté listo
    setTimeout(function() {
        const iframe = window.parent.document.querySelector('iframe[title="streamlit_app"]') || window.parent.document;
        const doc = iframe.contentDocument || iframe.document || window.parent.document;
        
        // Obtener audios
        const audioMain = doc.getElementById('audioMain');
        const hoverPrev = doc.getElementById('hoverPrev');
        const hoverPlay = doc.getElementById('hoverPlay');
        const hoverNext = doc.getElementById('hoverNext');
        
        // Obtener botones usando data-testid
        const buttons = doc.querySelectorAll('button[data-testid*="baseButton"]');
        let btnPrev, btnPlay, btnNext;
        
        buttons.forEach(btn => {
            const text = btn.textContent || btn.innerText;
            if (text.includes('Anterior')) btnPrev = btn;
            else if (text.includes('Reproducir')) btnPlay = btn;
            else if (text.includes('Siguiente')) btnNext = btn;
        });
        
        // Función play/pause
        if (btnPlay && audioMain) {
            btnPlay.addEventListener('click', function() {
                if (audioMain.paused) {
                    audioMain.play();
                } else {
                    audioMain.pause();
                }
            });
        }
        
        // Eventos hover
        if (btnPrev && hoverPrev) {
            btnPrev.addEventListener('mouseenter', function() {
                hoverPrev.currentTime = 0;
                hoverPrev.play();
            });
        }
        
        if (btnPlay && hoverPlay) {
            btnPlay.addEventListener('mouseenter', function() {
                hoverPlay.currentTime = 0;
                hoverPlay.play();
            });
        }
        
        if (btnNext && hoverNext) {
            btnNext.addEventListener('mouseenter', function() {
                hoverNext.currentTime = 0;
                hoverNext.play();
            });
        }
    }, 1000);
    </script>
    """, unsafe_allow_html=True)

else:
    st.info("Por favor, sube un archivo .ipynb para comenzar.")
    st.markdown("📢 Este lector te guiará con audio paso a paso una vez cargues el archivo.")

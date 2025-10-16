import streamlit as st
import nbformat
from gtts import gTTS
import base64
import io
import re

st.set_page_config(page_title="Lector Inclusivo de Notebook", layout="centered")

# --- Función para convertir texto a audio (mp3 en base64) ---
def text_to_audio_base64(text, lang="es"):
    try:
        tts = gTTS(text=text, lang=lang, tld="com.mx")  # Español latino (México)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    except:
        # Fallback sin tld si falla
        tts = gTTS(text=text, lang=lang)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()

# --- Limpieza de texto ---
def limpiar_texto(texto):
    texto = re.sub(r"#+", "", texto)
    texto = re.sub(r"[\*\_\~\`\>\-]", "", texto)
    texto = texto.strip()
    return texto

# --- Detectar fórmulas y tablas ---
def detectar_contenido_especial(texto):
    avisos = []
    # Detectar fórmulas LaTeX
    if re.search(r'\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\)', texto):
        avisos.append("Atención: este fragmento contiene fórmulas matemáticas.")
    # Detectar tablas markdown
    if re.search(r'\|.*\|.*\|', texto):
        avisos.append("Atención: este fragmento contiene una tabla.")
    # Detectar código con muchas líneas
    if texto.count('\n') > 10:
        avisos.append("Atención: este fragmento contiene código extenso.")
    return avisos

# --- Descripción automática del tipo de contenido ---
def describir_para_usuario(tipo, texto):
    texto_limpio = limpiar_texto(texto)
    descripcion = ""
    
    if tipo == "code":
        descripcion = "A continuación verás una celda de código en Python."
    elif tipo == "markdown":
        descripcion = "A continuación escucharás texto explicativo."
    elif tipo == "output":
        descripcion = "A continuación escucharás el resultado de una ejecución."
    else:
        descripcion = "Contenido del notebook."
    
    # Agregar avisos de contenido especial
    avisos = detectar_contenido_especial(texto)
    if avisos:
        descripcion += " " + " ".join(avisos)
    
    return descripcion

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
        chunks.append({
            'texto_completo': f"{descripcion} {contenido}",
            'texto_visual': texto[:500]
        })
    return chunks

# --- Inicialización de variables de sesión ---
if "chunks" not in st.session_state:
    st.session_state.chunks = []
if "index" not in st.session_state:
    st.session_state.index = 0
if "audio_cache" not in st.session_state:
    st.session_state.audio_cache = {}
if "playing" not in st.session_state:
    st.session_state.playing = True

# --- Generar audio único por ID ---
def get_audio_for_chunk(idx):
    if idx not in st.session_state.audio_cache:
        texto = st.session_state.chunks[idx]['texto_completo']
        audio_b64 = text_to_audio_base64(texto)
        st.session_state.audio_cache[idx] = audio_b64
    return st.session_state.audio_cache[idx]

# --- Generar audios de hover (solo una vez) ---
def get_hover_audios():
    if 'hover_audios' not in st.session_state:
        st.session_state.hover_audios = {
            'prev': text_to_audio_base64("Botón anterior"),
            'play': text_to_audio_base64("Botón reproducir o pausar"),
            'next': text_to_audio_base64("Botón siguiente")
        }
    return st.session_state.hover_audios

# --- Subida de archivo ---
st.title("🧠 Lector inclusivo de notebooks (.ipynb)")
archivo = st.file_uploader("Por favor, carga tu archivo .ipynb", type=["ipynb"])

# --- Procesamiento del archivo ---
if archivo:
    # Resetear chunks si se sube un nuevo archivo
    file_key = f"{archivo.name}_{archivo.size}"
    if "file_key" not in st.session_state or st.session_state.file_key != file_key:
        st.session_state.chunks = []
        st.session_state.audio_cache = {}
        st.session_state.file_key = file_key
        st.session_state.index = 0
    
    if not st.session_state.chunks:
        st.session_state.chunks = procesar_notebook(archivo)
        st.session_state.index = 0

    current_idx = st.session_state.index
    total = len(st.session_state.chunks)

    st.markdown(f"### Fragmento {current_idx + 1} de {total}")
    st.text_area("Texto actual:", st.session_state.chunks[current_idx]['texto_visual'], height=200, key=f"textarea_{current_idx}")

    # --- Obtener audio del fragmento actual ---
    audio_b64 = get_audio_for_chunk(current_idx)
    hover_audios = get_hover_audios()
    
    # --- Controles accesibles ---
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("⏮️ Anterior", use_container_width=True, key=f"btn_prev_{current_idx}"):
            if st.session_state.index > 0:
                st.session_state.index -= 1
                st.session_state.playing = True
                st.rerun()

    with col2:
        if st.button("⏯️ Reproducir/Pausar", use_container_width=True, key=f"btn_play_{current_idx}"):
            st.session_state.playing = not st.session_state.playing
            st.rerun()

    with col3:
        if st.button("⏭️ Siguiente", use_container_width=True, key=f"btn_next_{current_idx}"):
            if st.session_state.index < total - 1:
                st.session_state.index += 1
                st.session_state.playing = True
                st.rerun()

    # --- HTML con audio y JavaScript integrado ---
    autoplay = "autoplay" if st.session_state.playing else ""
    
    st.markdown(f"""
    <div id="audio-container">
        <audio id="mainAudio" {autoplay} controls style="width: 100%; margin: 20px 0;">
            <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
        </audio>
        
        <audio id="hoverPrev" preload="auto">
            <source src="data:audio/mp3;base64,{hover_audios['prev']}" type="audio/mp3">
        </audio>
        <audio id="hoverPlay" preload="auto">
            <source src="data:audio/mp3;base64,{hover_audios['play']}" type="audio/mp3">
        </audio>
        <audio id="hoverNext" preload="auto">
            <source src="data:audio/mp3;base64,{hover_audios['next']}" type="audio/mp3">
        </audio>
    </div>
    
    <script>
        // Función para configurar eventos hover
        function setupHoverEvents() {{
            const parentDoc = window.parent.document;
            const buttons = parentDoc.querySelectorAll('button[data-testid="baseButton-secondary"]');
            
            const hoverPrev = document.getElementById('hoverPrev');
            const hoverPlay = document.getElementById('hoverPlay');
            const hoverNext = document.getElementById('hoverNext');
            
            buttons.forEach((btn) => {{
                const text = btn.textContent;
                
                // Remover eventos previos
                btn.onmouseenter = null;
                
                if (text.includes('Anterior') && hoverPrev) {{
                    btn.onmouseenter = function() {{
                        hoverPrev.currentTime = 0;
                        hoverPrev.play().catch(e => {{}});
                    }};
                }} 
                else if (text.includes('Reproducir') && hoverPlay) {{
                    btn.onmouseenter = function() {{
                        hoverPlay.currentTime = 0;
                        hoverPlay.play().catch(e => {{}});
                    }};
                }} 
                else if (text.includes('Siguiente') && hoverNext) {{
                    btn.onmouseenter = function() {{
                        hoverNext.currentTime = 0;
                        hoverNext.play().catch(e => {{}});
                    }};
                }}
            }});
        }}
        
        // Intentar configurar múltiples veces
        setTimeout(setupHoverEvents, 100);
        setTimeout(setupHoverEvents, 300);
        setTimeout(setupHoverEvents, 600);
        setTimeout(setupHoverEvents, 1000);
    </script>
    """, unsafe_allow_html=True)

else:
    st.info("Por favor, sube un archivo .ipynb para comenzar.")
    st.markdown("📢 Este lector te guiará con audio paso a paso. Detecta automáticamente fórmulas, tablas y código extenso.")

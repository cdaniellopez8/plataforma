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
        tts = gTTS(text=text, lang=lang, tld="com.co")  # Español latino (México)
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

# --- Generar audio único por ID ---
def get_audio_for_chunk(idx):
    if idx not in st.session_state.audio_cache:
        texto = st.session_state.chunks[idx]['texto_completo']
        audio_b64 = text_to_audio_base64(texto)
        st.session_state.audio_cache[idx] = f"data:audio/mp3;base64,{audio_b64}"
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
    if not st.session_state.chunks:
        st.session_state.chunks = procesar_notebook(archivo)
        st.session_state.index = 0

    current_idx = st.session_state.index
    total = len(st.session_state.chunks)

    st.markdown(f"### Fragmento {current_idx + 1} de {total}")
    st.text_area("Texto actual:", st.session_state.chunks[current_idx]['texto_visual'], height=200)

    # --- Obtener audio del fragmento actual ---
    audio_src = get_audio_for_chunk(current_idx)
    hover_audios = get_hover_audios()
    
    # ID único para el audio basado en el índice
    audio_id = f"audioMain_{current_idx}"
    
    # --- Reproduce el audio principal ---
    st.markdown(f"""
    <audio id="{audio_id}" autoplay controls style="width: 100%; margin-bottom: 20px;">
        <source src="{audio_src}" type="audio/mp3">
    </audio>
    """, unsafe_allow_html=True)

    # --- Audios hover (ocultos) ---
    st.markdown(f"""
    <audio id="hoverPrev" preload="auto"></audio>
    <audio id="hoverPlay" preload="auto"></audio>
    <audio id="hoverNext" preload="auto"></audio>
    """, unsafe_allow_html=True)

    # --- Controles accesibles ---
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("⏮️ Anterior", use_container_width=True, key=f"btn_prev_{current_idx}"):
            if st.session_state.index > 0:
                st.session_state.index -= 1
                st.rerun()

    with col2:
        st.button("⏯️ Reproducir/Pausar", use_container_width=True, key=f"btn_play_{current_idx}")

    with col3:
        if st.button("⏭️ Siguiente", use_container_width=True, key=f"btn_next_{current_idx}"):
            if st.session_state.index < total - 1:
                st.session_state.index += 1
                st.rerun()

    # --- JavaScript mejorado para controlar audio y hover ---
    st.markdown(f"""
    <script>
    (function() {{
        // Cargar audios hover
        const hoverPrev = document.getElementById('hoverPrev');
        const hoverPlay = document.getElementById('hoverPlay');
        const hoverNext = document.getElementById('hoverNext');
        
        hoverPrev.src = "data:audio/mp3;base64,{hover_audios['prev']}";
        hoverPlay.src = "data:audio/mp3;base64,{hover_audios['play']}";
        hoverNext.src = "data:audio/mp3;base64,{hover_audios['next']}";
        
        // Función para encontrar el audio principal
        function getMainAudio() {{
            return document.getElementById('{audio_id}');
        }}
        
        // Función para encontrar botones
        function setupButtons() {{
            const buttons = window.parent.document.querySelectorAll('button[kind="secondary"]');
            
            buttons.forEach((btn, idx) => {{
                const text = btn.textContent || btn.innerText;
                
                if (text.includes('Anterior')) {{
                    btn.onmouseenter = () => {{
                        hoverPrev.currentTime = 0;
                        hoverPrev.play().catch(e => console.log('Audio hover bloqueado'));
                    }};
                }}
                else if (text.includes('Reproducir') || text.includes('Pausar')) {{
                    btn.onclick = (e) => {{
                        const audio = getMainAudio();
                        if (audio) {{
                            if (audio.paused) {{
                                audio.play();
                            }} else {{
                                audio.pause();
                            }}
                        }}
                    }};
                    btn.onmouseenter = () => {{
                        hoverPlay.currentTime = 0;
                        hoverPlay.play().catch(e => console.log('Audio hover bloqueado'));
                    }};
                }}
                else if (text.includes('Siguiente')) {{
                    btn.onmouseenter = () => {{
                        hoverNext.currentTime = 0;
                        hoverNext.play().catch(e => console.log('Audio hover bloqueado'));
                    }};
                }}
            }});
        }}
        
        // Ejecutar con retry
        setTimeout(setupButtons, 100);
        setTimeout(setupButtons, 500);
        setTimeout(setupButtons, 1000);
    }})();
    </script>
    """, unsafe_allow_html=True)

else:
    st.info("Por favor, sube un archivo .ipynb para comenzar.")
    st.markdown("📢 Este lector te guiará con audio paso a paso. Detecta automáticamente fórmulas, tablas y código extenso.")


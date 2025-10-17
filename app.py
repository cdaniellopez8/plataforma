import streamlit as st
import nbformat
from openai import OpenAI
import re
import base64
import streamlit.components.v1 as components 

# Inicializar cliente de OpenAI
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception:
    st.error("🚨 Error: No se encontró la clave API de OpenAI. Asegúrate de tenerla en st.secrets['OPENAI_API_KEY'].")
    st.stop()
    
st.set_page_config(layout="wide")
st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")
st.write("""
Esta aplicación convierte notebooks de Jupyter en una experiencia auditiva accesible.
El sistema te guiará con audios que explican el contenido.
""")

# -------------------------
# Audio de bienvenida y Funciones TTS (se mantiene sin cambios)
# -------------------------
if "audio_bienvenida_reproducido" not in st.session_state:
    st.session_state.audio_bienvenida_reproducido = False

if not st.session_state.audio_bienvenida_reproducido:
    texto_bienvenida = """
    Bienvenido al Lector Inclusivo de Notebooks. 
    Esta aplicación te permite escuchar el contenido de archivos de Jupyter Notebook de forma accesible.
    Para comenzar, por favor sube tu archivo de notebook usando el botón que aparece a continuación.
    """
    with st.spinner("🎵 Preparando audio de bienvenida..."):
        try:
            audio_bienvenida = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="alloy",
                input=texto_bienvenida
            )
            audio_bytes = audio_bienvenida.read()
            st.markdown("### 🔊 Audio de bienvenida")
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)
        except Exception:
            st.warning("No fue posible generar el audio de bienvenida automáticamente.")
    st.session_state.audio_bienvenida_reproducido = True

uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

# -------------------------
# Detección del tipo de contenido
# -------------------------
def detectar_tipo_contenido(texto):
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):
        return "tabla"
    elif re.search(r"(!\[.*\]\(.*\))|(\\includegraphics)", texto):
        return "grafico"
    else:
        return "texto"

# -------------------------
# Descripción guiada según tipo (PROMPT DE TABLA CORREGIDO)
# -------------------------
def describir_contenido(tipo, texto):
    if tipo == "formula":
        prompt = f"""
Eres un asistente que apoya a personas ciegas leyendo notebooks. Vas a generar una frase introductoria breve con este formato:
"A continuación **escucharás** una explicación. Esta trata sobre [explicación corta del tema de la fórmula, sin decir qué es ni usar símbolos]. La fórmula en sí es compleja y se presenta a continuación como texto."
No repitas la fórmula, ni la leas como símbolos. Usa lenguaje accesible.
Contenido: {texto[:800]}
"""
    elif tipo == "tabla":
        # ⭐⭐⭐ PROMPT CORREGIDO: Enfatiza la estructura (columnas y tipos) Y el resumen ⭐⭐⭐
        prompt = f"""
Eres un asistente que apoya a personas ciegas leyendo notebooks. El contenido es una tabla de datos.
Tu tarea es describir la tabla de la manera más accesible y útil.
Instrucciones:
1. Comienza diciendo: "A continuación, **escucharás** la descripción de una tabla de datos. Sus columnas son:"
2. **LEE CLARAMENTE** cada nombre de columna seguido de su tipo de dato inferido. Por ejemplo: 'Columna ID (Identificador)', 'Nombre del Producto (Texto)', 'Precio (Numérico/Moneda)'.
3. **FINALMENTE**, agrega un resumen conciso sobre el propósito o el contenido general de los datos.
Contenido de la tabla: {texto[:1000]}
"""
    elif tipo == "grafico":
        prompt = f"""
Eres un asistente que apoya a personas ciegas leyendo notebooks. El contenido es un gráfico o visualización de datos.
Tu tarea es proporcionar una **descripción verbal concisa y útil** del gráfico.
Instrucciones:
1. Comienza diciendo: "A continuación, **escucharás** la descripción de un gráfico. "
2. Describe el TIPO de gráfico (Ej: "Es un gráfico de barras").
3. Describe qué representan los EJES (Ej: "El eje X muestra el Tiempo y el eje Y muestra la Temperatura").
4. Describe el HALLAZGO CLAVE o la tendencia principal.
Contenido que genera el gráfico o texto asociado: {texto[:1000]}
"""
    elif tipo == "código":
        prompt = f"""
Eres un asistente que apoya a personas ciegas leyendo notebooks. El contenido es código Python.
Explica en una frase corta y sencilla qué hace el código y luego explica cada paso importante.
Código: {texto[:1000]}
"""
    else:
        prompt = texto

    if tipo == "texto":
        return prompt
    else:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5
            )
            return response.choices[0].message.content
        except Exception:
            return f"No fue posible generar la descripción de {tipo}."

# -------------------------
# Conversión y TTS (se mantiene sin cambios)
# -------------------------
def latex_a_texto_hablado(formula):
    texto = formula.replace('$', '').replace('\\(', '').replace('\\)', '').replace('\\[', '').replace('\\]', '')
    reemplazos = {
        '^2': ' al cuadrado', '^3': ' al cubo', '^{2}': ' al cuadrado', '^{3}': ' al cubo',
        '\\times': ' por', '\\cdot': ' por', '\\frac': ' fracción', '\\sqrt': ' raíz cuadrada de',
        '\\alpha': ' alfa', '\\beta': ' beta', '\\gamma': ' gamma', '\\delta': ' delta',
        '\\pi': ' pi', '\\theta': ' theta', '\\sum': ' sumatoria', '\\int': ' integral',
        '\\infty': ' infinito', '\\pm': ' más menos', '\\leq': ' menor o igual',
        '\\geq': ' mayor o igual', '=': ' igual a ', '+': ' más ', '-': ' menos ', '*': ' por ',
    }
    for latex, natural in reemplazos.items():
        texto = texto.replace(latex, natural)
    texto = re.sub(r'[{}\\]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def text_to_speech(text):
    try:
        audio_response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text
        )
        return audio_response.read()
    except Exception:
        return b""

# -------------------------
# Procesamiento del archivo (se mantiene sin cambios)
# -------------------------
if uploaded_file is not None:
    # Reiniciar completamente el estado si se carga un archivo nuevo
    if "uploaded_file_name" not in st.session_state or st.session_state.uploaded_file_name != uploaded_file.name:
        st.session_state.bloques_audio = []
        st.session_state.indice_actual = 0
        st.session_state.indice_audio_bloque = 0
        st.session_state.notebook_cargado = False
        st.session_state.uploaded_file_name = uploaded_file.name

    # Procesar notebook solo una vez
    if not st.session_state.notebook_cargado:
        try:
            notebook = nbformat.read(uploaded_file, as_version=4)
        except Exception as e:
            st.error(f"Error al leer el archivo .ipynb: {e}")
            st.stop()

        bloques = []
        with st.spinner("📚 Procesando notebook..."):
            for i, cell in enumerate(notebook.cells, 1):
                cell_type = cell["cell_type"]
                cell_source = cell["source"].strip()
                if not cell_source:
                    continue

                tipo = detectar_tipo_contenido(cell_source)

                bloque = {
                    "numero": i,
                    "tipo_celda": cell_type,
                    "tipo_contenido": tipo,
                    "contenido": cell_source,
                    "audios": []
                }

                # Generar audios según el tipo
                if cell_type == "markdown" and tipo == "texto":
                    audio_bytes = text_to_speech(cell_source)
                    bloque["audios"].append({"descripcion": "Texto", "bytes": audio_bytes, "mostrar_contenido": True})

                elif cell_type == "markdown" and tipo in ["formula", "tabla", "grafico"]: 
                    explicacion = describir_contenido(tipo, cell_source)
                    audio_explicacion = text_to_speech(explicacion) 
                    
                    contenido_legible = ""
                    if tipo == "formula":
                        try:
                            prompt_formula = f"Convierte esta fórmula matemática a lenguaje hablado natural en español. Fórmula: {cell_source}"
                            response_formula = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt_formula}], temperature=0.3, max_tokens=200)
                            contenido_legible = response_formula.choices[0].message.content
                        except Exception:
                            contenido_legible = latex_a_texto_hablado(cell_source)
                        audio_contenido = text_to_speech(contenido_legible)
                    else: # tabla o grafico
                        audio_contenido = text_to_speech("Contenido visual principal.")
                    
                    bloque["audios"].append({"descripcion": f"Descripción de {tipo}", "texto": explicacion, "bytes": audio_explicacion, "mostrar_contenido": False})
                    bloque["audios"].append({"descripcion": f"Contenido de {tipo}", "bytes": audio_contenido, "mostrar_contenido": True})

                elif cell_type == "code":
                    explicacion = describir_contenido("código", cell_source)
                    audio_explicacion = text_to_speech(explicacion)
                    bloque["audios"].append({"descripcion": "Explicación del código", "texto": explicacion, "bytes": audio_explicacion, "mostrar_contenido": False})

                if bloque["audios"]:
                     bloques.append(bloque)


        st.session_state.bloques_audio = bloques
        st.session_state.indice_actual = 0
        st.session_state.indice_audio_bloque = 0
        st.session_state.notebook_cargado = True
        st.success(f"✅ Notebook procesado: {len(bloques)} bloques encontrados")

    # Mostrar bloque actual
    if st.session_state.bloques_audio and len(st.session_state.bloques_audio) > 0:
        indice = st.session_state.indice_actual
        total_bloques = len(st.session_state.bloques_audio)

        if indice >= total_bloques: st.session_state.indice_actual = 0; indice = 0
        bloque_actual = st.session_state.bloques_audio[indice]
        total_audios_bloque = len(bloque_actual["audios"])
        indice_audio = st.session_state.indice_audio_bloque
        if indice_audio >= total_audios_bloque: st.session_state.indice_audio_bloque = 0; indice_audio = 0
        
        # Generar audios hover (manteniendo la lógica de generación)
        if "hover_audios_generados" not in st.session_state:
            try:
                st.session_state.audio_hover_anterior = text_to_speech("Anterior")
                st.session_state.audio_hover_siguiente = text_to_speech("Siguiente")
                st.session_state.audio_hover_reiniciar = text_to_speech("Reiniciar")
            except Exception:
                st.session_state.audio_hover_anterior = b""
                st.session_state.audio_hover_siguiente = b""
                st.session_state.audio_hover_reiniciar = b""
            st.session_state.hover_audios_generados = True

        # Insertar audios hover ocultos (si existen)
        audio_anterior_b64 = base64.b64encode(st.session_state.audio_hover_anterior).decode() if st.session_state.audio_hover_anterior else ""
        audio_siguiente_b64 = base64.b64encode(st.session_state.audio_hover_siguiente).decode() if st.session_state.audio_hover_siguiente else ""
        audio_reiniciar_b64 = base64.b64encode(st.session_state.audio_hover_reiniciar).decode() if st.session_state.audio_hover_reiniciar else ""

        st.markdown(f"""
        <audio id="hoverAnterior" preload="auto">
            <source src="data:audio/mp3;base64,{audio_anterior_b64}" type="audio/mp3">
        </audio>
        <audio id="hoverSiguiente" preload="auto">
            <source src="data:audio/mp3;base64,{audio_siguiente_b64}" type="audio/mp3">
        </audio>
        <audio id="hoverReiniciar" preload="auto">
            <source src="data:audio/mp3;base64,{audio_reiniciar_b64}" type="audio/mp3">
        </audio>
        """, unsafe_allow_html=True)
        
        # MOSTRAR BOTONES DE NAVEGACIÓN ANTES DEL CONTENIDO (Ubicación fija)
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("⏮️ Anterior", use_container_width=True, key="btn_anterior"):
                if st.session_state.indice_audio_bloque > 0:
                    st.session_state.indice_audio_bloque -= 1
                    st.rerun()
                elif st.session_state.indice_actual > 0:
                    st.session_state.indice_actual -= 1
                    st.session_state.indice_audio_bloque = len(st.session_state.bloques_audio[st.session_state.indice_actual]["audios"]) - 1
                    st.rerun()

        with col2:
            if st.button("🔄 Reiniciar", use_container_width=True, key="btn_reiniciar_fijo"):
                st.session_state.indice_audio_bloque = 0
                st.rerun()

        with col3:
            if st.button("⏭️ Siguiente", use_container_width=True, key="btn_siguiente"):
                if st.session_state.indice_audio_bloque < total_audios_bloque - 1:
                    st.session_state.indice_audio_bloque += 1
                    st.rerun()
                elif st.session_state.indice_actual >= total_bloques - 1:
                    texto_final = "Has llegado al final del documento"
                    audio_final = text_to_speech(texto_final)
                    st.audio(audio_final, format="audio/mp3", autoplay=True)
                    st.info("✅ " + texto_final)
                else:
                    st.session_state.indice_actual += 1
                    st.session_state.indice_audio_bloque = 0
                    st.rerun()
        
        st.markdown("---") # Separador visual

        # Mostrar el contenido del bloque
        st.markdown(f"### 📍 Bloque {bloque_actual['numero']} de {total_bloques}")

        if total_audios_bloque > 1:
            st.markdown(f"**Audio {indice_audio + 1} de {total_audios_bloque} en este bloque**")

        audio_info = bloque_actual["audios"][indice_audio]

        if "texto" in audio_info:
            st.write(audio_info["texto"])

        if audio_info.get("bytes"):
            st.audio(audio_info["bytes"], format="audio/mp3", autoplay=True)
        else:
            st.info("Audio no disponible para este bloque.")

        if audio_info["mostrar_contenido"]:
            if bloque_actual["tipo_celda"] == "code":
                st.code(bloque_actual["contenido"], language="python")
            else:
                st.markdown(bloque_actual["contenido"])


# ----------------------------------------------------
# FIX DE ACCESIBILIDAD CON TECLADO Y HOVER (se mantiene sin cambios)
# ----------------------------------------------------
components.html("""
<script>
// --- UTILITY FUNCTIONS ---
function findButtonByTestId(key) {
    const testId = `st.button-${key}`;
    let container = document.querySelector(`[data-testid="${testId}"]`);
    if (!container && window.parent && window.parent.document) {
        container = window.parent.document.querySelector(`[data-testid="${testId}"]`);
    }
    return container ? container.querySelector('button') : null;
}

// --- FIX TECLADO (Flechas y R) ---
document.addEventListener('keydown', function(event) {
    const active = document.activeElement;
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable)) {
        return;
    }

    const ANTERIOR_KEY = 'btn_anterior';
    const SIGUIENTE_KEY = 'btn_siguiente';
    const REINICIAR_KEY = 'btn_reiniciar_fijo'; 
    
    let targetButton = null;

    if (event.key === 'ArrowLeft') {
        targetButton = findButtonByTestId(ANTERIOR_KEY);
    } else if (event.key === 'ArrowRight') {
        targetButton = findButtonByTestId(SIGUIENTE_KEY);
    } else if (event.key.toLowerCase() === 'r') {
        targetButton = findButtonByTestId(REINICIAR_KEY);
    }

    if (targetButton) {
        event.preventDefault(); 
        targetButton.click();
    }
}, true);

// --- HOVER AUDIO ---
function attachHoverAudio() {
    const hoverMappings = [
        { key: 'btn_anterior', audioId: 'hoverAnterior' },
        { key: 'btn_siguiente', audioId: 'hoverSiguiente' },
        { key: 'btn_reiniciar_fijo', audioId: 'hoverReiniciar' }
    ];

    hoverMappings.forEach(mapping => {
        const button = findButtonByTestId(mapping.key);
        const audio = document.getElementById(mapping.audioId);

        if (button && audio) {
            button.onmouseenter = function() {
                audio.pause();
                audio.currentTime = 0;
                audio.play().catch(e => console.error("Error al reproducir audio:", e));
            };
            button.onmouseleave = function() {
                audio.pause();
                audio.currentTime = 0;
            };
        }
    });
}

attachHoverAudio();

const observerTarget = document.body || document;
const observer = new MutationObserver(function(mutations) {
    attachHoverAudio();
});

observer.observe(observerTarget, { childList: true, subtree: true, attributes: false });
</script>
""", height=0)

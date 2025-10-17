import streamlit as st
import nbformat
from openai import OpenAI
import re
import base64

# Inicializar cliente de OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")
st.write("""
Esta aplicación convierte notebooks de Jupyter en una experiencia auditiva accesible.
- Si el bloque es **texto**, lo leerá directamente.
- Si contiene **una fórmula**, dirá primero: *"A continuación verás una fórmula, esta trata sobre..."*
- Si contiene **una tabla**, dirá primero: *"A continuación verás una tabla con las siguientes columnas..."* y luego leerá cada columna y su tipo.
""")

# -------------------------
# Audio de bienvenida
# -------------------------
if "audio_bienvenida_reproducido" not in st.session_state:
    st.session_state.audio_bienvenida_reproducido = False

if not st.session_state.audio_bienvenida_reproducido:
    texto_bienvenida = """
    Bienvenido al Lector Inclusivo de Notebooks. 
    Esta aplicación te permite escuchar el contenido de archivos de Jupyter Notebook de forma accesible.
    
    Funciona de la siguiente manera:
    - Cuando subas un archivo punto ipynb, el sistema lo analizará automáticamente.
    - Si encuentra texto, lo leerá directamente.
    - Si encuentra una fórmula matemática, primero te explicará de qué trata antes de mostrarla.
    - Si encuentra una tabla, te describirá las columnas y sus tipos de datos.
    - Para el código, te dará una explicación de lo que hace.
    
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
        except Exception as e:
            # Falla silenciosa si la TTS no está disponible en el entorno
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
    else:
        return "texto"

# -------------------------
# Descripción guiada según tipo
# -------------------------
def describir_contenido(tipo, texto):
    if tipo == "formula":
        prompt = f"""
Eres un asistente que apoya a personas ciegas leyendo notebooks. Vas a generar una frase introductoria breve con este formato:
"A continuación verás una fórmula. Esta trata sobre [explicación corta del tema de la fórmula, sin decir qué es ni usar símbolos]."
No repitas la fórmula, ni la leas como símbolos, ni digas 'aquí hay una fórmula matemática'.
Contenido: {texto[:800]}
"""
    elif tipo == "tabla":
        prompt = f"""
Eres un asistente que apoya a personas ciegas leyendo notebooks. El contenido es una tabla.
Primero di: "A continuación verás una tabla con las siguientes columnas:"
Luego, menciona cada columna junto con su tipo de dato inferido (numérica, texto, identificador, fecha, etc.).
Contenido: {texto[:1000]}
"""
    else:
        prompt = texto

    if tipo == "texto":
        return prompt
    else:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        return response.choices[0].message.content

# -------------------------
# Conversión LaTeX a texto hablado
# -------------------------
def latex_a_texto_hablado(formula):
    texto = formula.replace('$', '').replace('\\(', '').replace('\\)', '').replace('\\[', '').replace('\\]', '')
    reemplazos = {
        '^2': ' al cuadrado',
        '^3': ' al cubo',
        '^{2}': ' al cuadrado',
        '^{3}': ' al cubo',
        '\\times': ' por',
        '\\cdot': ' por',
        '\\frac': ' fracción',
        '\\sqrt': ' raíz cuadrada de',
        '\\alpha': ' alfa',
        '\\beta': ' beta',
        '\\gamma': ' gamma',
        '\\delta': ' delta',
        '\\pi': ' pi',
        '\\theta': ' theta',
        '\\sum': ' sumatoria',
        '\\int': ' integral',
        '\\infty': ' infinito',
        '\\pm': ' más menos',
        '\\leq': ' menor o igual',
        '\\geq': ' mayor o igual',
        '=': ' igual a ',
        '+': ' más ',
        '-': ' menos ',
        '*': ' por ',
    }
    for latex, natural in reemplazos.items():
        texto = texto.replace(latex, natural)
    texto = re.sub(r'[{}\\]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

# -------------------------
# Texto a voz
# -------------------------
def text_to_speech(text):
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return audio_response.read()

# -------------------------
# Procesamiento del archivo
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
        notebook = nbformat.read(uploaded_file, as_version=4)
        bloques = []
        with st.spinner("📚 Procesando notebook..."):
            for i, cell in enumerate(notebook.cells, 1):
                cell_type = cell["cell_type"]
                cell_source = cell["source"].strip()
                if not cell_source:
                    continue

                tipo = detectar_tipo_contenido(cell_source)

                # Crear estructura de bloque
                bloque = {
                    "numero": i,
                    "tipo_celda": cell_type,
                    "tipo_contenido": tipo,
                    "contenido": cell_source,
                    "audios": []
                }

                # Generar audios según el tipo
                if cell_type == "markdown" and tipo == "texto":
                    try:
                        audio_bytes = text_to_speech(cell_source)
                    except Exception:
                        audio_bytes = b""
                    bloque["audios"].append({
                        "descripcion": "Texto",
                        "bytes": audio_bytes,
                        "mostrar_contenido": True
                    })

                elif cell_type == "markdown" and tipo in ["formula", "tabla"]:
                    explicacion = describir_contenido(tipo, cell_source)
                    try:
                        audio_explicacion = text_to_speech(explicacion)
                    except Exception:
                        audio_explicacion = b""

                    if tipo == "formula":
                        try:
                            prompt_formula = f"""
Convierte esta fórmula matemática a lenguaje hablado natural en español. 
NO uses letras sueltas. Usa frases completas y naturales.
Ejemplo: E=mc^2 debe decirse como "E igual a m por c al cuadrado"

Fórmula: {cell_source}
"""
                            response_formula = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "user", "content": prompt_formula}],
                                temperature=0.3,
                                max_tokens=200
                            )
                            contenido_legible = response_formula.choices[0].message.content
                        except Exception:
                            contenido_legible = latex_a_texto_hablado(cell_source)
                        try:
                            audio_contenido = text_to_speech(contenido_legible)
                        except Exception:
                            audio_contenido = b""
                    else:
                        try:
                            audio_contenido = text_to_speech(cell_source)
                        except Exception:
                            audio_contenido = b""

                    bloque["audios"].append({
                        "descripcion": f"Descripción de {tipo}",
                        "texto": explicacion,
                        "bytes": audio_explicacion,
                        "mostrar_contenido": False
                    })
                    bloque["audios"].append({
                        "descripcion": f"Contenido de {tipo}",
                        "bytes": audio_contenido,
                        "mostrar_contenido": True
                    })

                elif cell_type == "code":
                    explicacion = describir_contenido("código", cell_source)
                    try:
                        audio_explicacion = text_to_speech(explicacion)
                    except Exception:
                        audio_explicacion = b""
                    bloque["audios"].append({
                        "descripcion": "Explicación del código",
                        "texto": explicacion,
                        "bytes": audio_explicacion,
                        "mostrar_contenido": False
                    })

                bloques.append(bloque)

        # Asegurar orden correcto por número de bloque (evita orden inesperado)
        bloques.sort(key=lambda b: b.get("numero", 0))

        st.session_state.bloques_audio = bloques
        st.session_state.indice_actual = 0
        st.session_state.indice_audio_bloque = 0
        st.session_state.notebook_cargado = True
        st.success(f"✅ Notebook procesado: {len(bloques)} bloques encontrados")

    # Mostrar bloque actual
    if st.session_state.bloques_audio and len(st.session_state.bloques_audio) > 0:
        indice = st.session_state.indice_actual
        total_bloques = len(st.session_state.bloques_audio)

        # Validar índice
        if indice >= total_bloques:
            st.session_state.indice_actual = 0
            indice = 0

        bloque_actual = st.session_state.bloques_audio[indice]
        total_audios_bloque = len(bloque_actual["audios"])
        indice_audio = st.session_state.indice_audio_bloque

        # Validar índice de audio
        if indice_audio >= total_audios_bloque:
            st.session_state.indice_audio_bloque = 0
            indice_audio = 0

        st.markdown(f"### 📍 Bloque {bloque_actual['numero']} de {total_bloques}")

        if total_audios_bloque > 1:
            st.markdown(f"**Audio {indice_audio + 1} de {total_audios_bloque} en este bloque**")

        # Mostrar el audio actual del bloque
        audio_info = bloque_actual["audios"][indice_audio]

        if "texto" in audio_info:
            st.write(audio_info["texto"])

        # Revisión segura: si los bytes están vacíos, no fallar
        if audio_info.get("bytes"):
            st.audio(audio_info["bytes"], format="audio/mp3", autoplay=True)
        else:
            st.info("Audio no disponible para este bloque.")

        if audio_info["mostrar_contenido"]:
            if bloque_actual["tipo_celda"] == "code":
                st.code(bloque_actual["contenido"], language="python")
            else:
                st.markdown(bloque_actual["contenido"])

        # Generar audios hover para botones (solo una vez)
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

        # Botones de navegación
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("⏮️ Anterior", use_container_width=True, key="btn_anterior"):
                if st.session_state.indice_actual > 0:
                    st.session_state.indice_actual -= 1
                    st.session_state.indice_audio_bloque = 0
                    st.rerun()

        with col2:
            if st.button("🔄 Reiniciar", use_container_width=True, key=f"btn_reiniciar_{indice}_{indice_audio}"):
                st.session_state.indice_audio_bloque = 0
                st.rerun()

        with col3:
            if st.button("⏭️ Siguiente", use_container_width=True, key="btn_siguiente"):
                if st.session_state.indice_audio_bloque < total_audios_bloque - 1:
                    st.session_state.indice_audio_bloque += 1
                    st.rerun()
                elif st.session_state.indice_actual >= total_bloques - 1:
                    texto_final = "Has llegado al final del documento"
                    try:
                        audio_final = text_to_speech(texto_final)
                        st.audio(audio_final, format="audio/mp3", autoplay=True)
                    except Exception:
                        pass
                    st.info("✅ " + texto_final)
                else:
                    st.session_state.indice_actual += 1
                    st.session_state.indice_audio_bloque = 0
                    st.rerun()

        # -------------------------
        # Accesibilidad con teclado - versión robusta
        # -------------------------
        st.markdown("""
        <script>
        (function() {
            // helper: busca botones por texto en doc y parentDoc
            function findButtons(doc) {
                if (!doc) return {};
                const allButtons = Array.from(doc.querySelectorAll('button'));
                let btnAnterior = null, btnSiguiente = null, btnReiniciar = null;
                allButtons.forEach(b => {
                    const text = (b.textContent || b.innerText || '').trim();
                    if (!btnAnterior && text.includes('Anterior')) btnAnterior = b;
                    if (!btnSiguiente && text.includes('Siguiente')) btnSiguiente = b;
                    if (!btnReiniciar && text.includes('Reiniciar')) btnReiniciar = b;
                });
                return { btnAnterior, btnSiguiente, btnReiniciar };
            }

            // attach key handler to a document if not already attached
            function attachKeyHandler(doc) {
                if (!doc || doc.__keyboardHandlerAttached) return;
                doc.__keyboardHandlerAttached = true;

                doc.addEventListener('keydown', function(event) {
                    // No interferir si el usuario está escribiendo
                    const active = doc.activeElement;
                    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable)) {
                        return;
                    }

                    // intentamos obtener botones del mismo documento y del parent
                    const fromDoc = findButtons(doc);
                    const parentDoc = (window.parent && window.parent.document && window.parent.document !== doc) ? window.parent.document : null;
                    const fromParent = findButtons(parentDoc);

                    // prefer btns en el mismo doc, si no existen, usar parent
                    const btnAnterior = fromDoc.btnAnterior || fromParent.btnAnterior;
                    const btnSiguiente = fromDoc.btnSiguiente || fromParent.btnSiguiente;
                    const btnReiniciar = fromDoc.btnReiniciar || fromParent.btnReiniciar;

                    try {
                        if (event.key === 'ArrowLeft' && btnAnterior) {
                            event.preventDefault();
                            btnAnterior.click();
                        } else if (event.key === 'ArrowRight' && btnSiguiente) {
                            event.preventDefault();
                            btnSiguiente.click();
                        } else if ((event.key === 'r' || event.key === 'R') && btnReiniciar) {
                            event.preventDefault();
                            btnReiniciar.click();
                        }
                    } catch (e) {
                        console.log('Error al simular click por teclado:', e);
                    }
                }, true);
            }

            // intentar adjuntar al document actual y al parent (si existe)
            try {
                attachKeyHandler(document);
                if (window.parent && window.parent.document && window.parent.document !== document) {
                    attachKeyHandler(window.parent.document);
                }
            } catch(e) {
                console.log('Error al adjuntar manejadores de teclado:', e);
            }

            // observer para cuando Streamlit renderice botones después
            const observerTarget = (document.body) ? document.body : document;
            const observer = new MutationObserver(function(mutations) {
                // cada vez que cambie el DOM, intentamos adjuntar (seguro y barato)
                try {
                    attachKeyHandler(document);
                    if (window.parent && window.parent.document && window.parent.document !== document) {
                        attachKeyHandler(window.parent.document);
                    }
                } catch(e) {}
            });
            observer.observe(observerTarget, { childList: true, subtree: true, attributes: false });

        })();
        </script>
        """, unsafe_allow_html=True)

import streamlit.components.v1 as components

# -------------------------
# Accesibilidad con teclado (funcional en Streamlit Cloud)
# -------------------------
components.html("""
<script>
document.addEventListener('keydown', function(event) {
    // Evitar que actúe cuando se escribe en inputs o textareas
    const active = document.activeElement;
    if (active && ['INPUT', 'TEXTAREA'].includes(active.tagName)) return;

    const buttons = Array.from(document.querySelectorAll('button'));
    let targetButton = null;

    if (event.key === 'ArrowLeft') {
        targetButton = buttons.find(b => b.innerText.includes('Anterior'));
    } else if (event.key === 'ArrowRight') {
        targetButton = buttons.find(b => b.innerText.includes('Siguiente'));
    } else if (event.key.toLowerCase() === 'r') {
        targetButton = buttons.find(b => b.innerText.includes('Reiniciar'));
    }

    if (targetButton) {
        event.preventDefault();
        targetButton.click();
    }
});
</script>
""", height=0)

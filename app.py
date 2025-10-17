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
    
    # Generar audio de bienvenida
    with st.spinner("🎵 Preparando audio de bienvenida..."):
        audio_bienvenida = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=texto_bienvenida
        )
        audio_bytes = audio_bienvenida.read()
    
    st.markdown("### 🔊 Audio de bienvenida")
    st.audio(audio_bytes, format="audio/mp3", autoplay=True)
    st.session_state.audio_bienvenida_reproducido = True

uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

# -------------------------
# Detección del tipo de contenido
# -------------------------
def detectar_tipo_contenido(texto):
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):  # fórmula LaTeX
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):  # tabla Markdown
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
Luego, menciona cada columna junto con su tipo de dato inferido (numérica, texto, identificador, fecha, etc.), en un formato claro, por ejemplo:
- columna edad, tipo numérica
- columna nombre, tipo texto
Si hay filas, indica cuántas aproximadamente hay.
Contenido: {texto[:1000]}
"""
    else:
        prompt = texto  # texto plano, no necesita descripción

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
# Convertir LaTeX a texto hablado
# -------------------------
def latex_a_texto_hablado(formula):
    """Convierte LaTeX simple a texto natural para TTS"""
    # Remover delimitadores de fórmula
    texto = formula.replace('$', '').replace('\\(', '').replace('\\)', '').replace('\\[', '').replace('\\]', '')
    
    # Reemplazos básicos de LaTeX a texto
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
    
    # Limpiar caracteres especiales restantes
    texto = re.sub(r'[{}\\]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    
    return texto.strip()

# -------------------------
# Conversión texto a voz
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
                    audio_bytes = text_to_speech(cell_source)
                    bloque["audios"].append({
                        "descripcion": "Texto",
                        "bytes": audio_bytes,
                        "mostrar_contenido": True
                    })
                
                elif cell_type == "markdown" and tipo in ["formula", "tabla"]:
                    explicacion = describir_contenido(tipo, cell_source)
                    audio_explicacion = text_to_speech(explicacion)
                    
                    # Para fórmulas, convertir LaTeX a texto natural
                    if tipo == "formula":
                        # Primero intentar con GPT para mejor calidad
                        try:
                            prompt_formula = f"""
Convierte esta fórmula matemática a lenguaje hablado natural en español. 
NO uses letras sueltas. Usa frases completas y naturales.
Ejemplo: E=mc^2 debe decirse como "E igual a m por c al cuadrado"

Fórmula: {cell_source}

Responde solo con el texto para leer en voz alta:"""
                            
                            response_formula = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "user", "content": prompt_formula}],
                                temperature=0.3,
                                max_tokens=200
                            )
                            contenido_legible = response_formula.choices[0].message.content
                        except:
                            # Si falla, usar conversión simple
                            contenido_legible = latex_a_texto_hablado(cell_source)
                        
                        audio_contenido = text_to_speech(contenido_legible)
                    else:
                        audio_contenido = text_to_speech(cell_source)
                    
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
                    audio_explicacion = text_to_speech(explicacion)
                    
                    bloque["audios"].append({
                        "descripcion": "Explicación del código",
                        "texto": explicacion,
                        "bytes": audio_explicacion,
                        "mostrar_contenido": False
                    })
                
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
        
        st.audio(audio_info["bytes"], format="audio/mp3", autoplay=True)
        
        if audio_info["mostrar_contenido"]:
            if bloque_actual["tipo_celda"] == "code":
                st.code(bloque_actual["contenido"], language="python")
            else:
                st.markdown(bloque_actual["contenido"])
        
        # Generar audios hover para botones (solo una vez)
        if "hover_audios_generados" not in st.session_state:
            st.session_state.audio_hover_anterior = text_to_speech("Anterior")
            st.session_state.audio_hover_siguiente = text_to_speech("Siguiente")
            st.session_state.audio_hover_reiniciar = text_to_speech("Reiniciar")
            st.session_state.hover_audios_generados = True
        
        # Insertar audios hover ocultos
        audio_anterior_b64 = base64.b64encode(st.session_state.audio_hover_anterior).decode()
        audio_siguiente_b64 = base64.b64encode(st.session_state.audio_hover_siguiente).decode()
        audio_reiniciar_b64 = base64.b64encode(st.session_state.audio_hover_reiniciar).decode()
        
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
                # Si hay más audios en el bloque actual
                if st.session_state.indice_audio_bloque < total_audios_bloque - 1:
                    st.session_state.indice_audio_bloque += 1
                    st.rerun()
                # Si es el último audio del último bloque
                elif st.session_state.indice_actual >= total_bloques - 1:
                    texto_final = "Has llegado al final del documento"
                    audio_final = text_to_speech(texto_final)
                    st.info("✅ " + texto_final)
                    st.audio(audio_final, format="audio/mp3", autoplay=True)
                # Avanzar al siguiente bloque
                else:
                    st.session_state.indice_actual += 1
                    st.session_state.indice_audio_bloque = 0
                    st.rerun()
        
        # JavaScript para manejar hover - MEJORADO
        st.markdown("""
        <script>
        // Ejecutar inmediatamente cuando se carga
        (function() {
            let hoversConfigurados = false;
            
            function initHover() {
                // Prevenir configuración duplicada
                if (hoversConfigurados) return true;
                
                // Buscar en el documento principal y en iframes
                let doc = document;
                const iframe = window.parent.document.querySelector('iframe');
                if (iframe && iframe.contentDocument) {
                    doc = iframe.contentDocument;
                }
                
                const hoverAnterior = doc.getElementById('hoverAnterior') || document.getElementById('hoverAnterior');
                const hoverSiguiente = doc.getElementById('hoverSiguiente') || document.getElementById('hoverSiguiente');
                const hoverReiniciar = doc.getElementById('hoverReiniciar') || document.getElementById('hoverReiniciar');
                
                if (!hoverAnterior || !hoverSiguiente || !hoverReiniciar) {
                    console.log('Audios no encontrados aún...');
                    return false;
                }
                
                // Buscar botones tanto en el documento como en el parent
                const allButtons = Array.from(doc.querySelectorAll('button')).concat(
                    Array.from(document.querySelectorAll('button'))
                );
                
                let btnAnterior, btnSiguiente, btnReiniciar;
                
                allButtons.forEach(btn => {
                    const text = btn.textContent || btn.innerText || '';
                    if (text.includes('Anterior') && !btnAnterior) btnAnterior = btn;
                    else if (text.includes('Siguiente') && !btnSiguiente) btnSiguiente = btn;
                    else if (text.includes('Reiniciar') && !btnReiniciar) btnReiniciar = btn;
                });
                
                console.log('Botones encontrados:', {
                    anterior: !!btnAnterior,
                    siguiente: !!btnSiguiente,
                    reiniciar: !!btnReiniciar
                });
                
                if (!btnAnterior || !btnSiguiente || !btnReiniciar) {
                    return false;
                }
                
                // Configurar eventos
                btnAnterior.onmouseenter = function() {
                    console.log('Hover Anterior');
                    hoverAnterior.currentTime = 0;
                    hoverAnterior.play().catch(e => console.log('Error anterior:', e));
                };
                
                btnSiguiente.onmouseenter = function() {
                    console.log('Hover Siguiente');
                    hoverSiguiente.currentTime = 0;
                    hoverSiguiente.play().catch(e => console.log('Error siguiente:', e));
                };
                
                btnReiniciar.onmouseenter = function() {
                    console.log('Hover Reiniciar');
                    hoverReiniciar.currentTime = 0;
                    hoverReiniciar.play().catch(e => console.log('Error reiniciar:', e));
                };
                
                hoversConfigurados = true;
                console.log('✅ Hovers configurados exitosamente');
                return true;
            }
            
            // Intentar configurar múltiples veces
            let attempts = 0;
            const maxAttempts = 20;
            const interval = setInterval(function() {
                attempts++;
                console.log('Intento', attempts, 'de configurar hovers...');
                if (initHover() || attempts >= maxAttempts) {
                    clearInterval(interval);
                    if (attempts >= maxAttempts) {
                        console.log('❌ No se pudieron configurar hovers después de', attempts, 'intentos');
                    }
                }
            }, 300);
        })();
        </script>
        """, unsafe_allow_html=True)

# -------------------------
# Accesibilidad con teclado
# -------------------------

st.markdown("""
<script>
document.addEventListener('keydown', function(event) {
    // Usa las teclas de flecha para navegar
    if (event.key === 'ArrowLeft') {
        // ⏮️ Anterior
        const btn = Array.from(document.querySelectorAll('button'))
            .find(b => b.textContent.includes('Anterior'));
        if (btn) btn.click();
    } else if (event.key === 'ArrowRight') {
        // ⏭️ Siguiente
        const btn = Array.from(document.querySelectorAll('button'))
            .find(b => b.textContent.includes('Siguiente'));
        if (btn) btn.click();
    } else if (event.key === 'r' || event.key === 'R') {
        // 🔄 Reiniciar (con tecla R)
        const btn = Array.from(document.querySelectorAll('button'))
            .find(b => b.textContent.includes('Reiniciar'));
        if (btn) btn.click();
    }
});
</script>
""", unsafe_allow_html=True)




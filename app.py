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
# Leer fórmulas correctamente
# -------------------------
def leer_formula_correctamente(texto):
    """Convierte fórmulas LaTeX a texto legible para TTS"""
    prompt = f"""
Eres un asistente que convierte fórmulas matemáticas en LaTeX a lenguaje natural en español para personas ciegas.

Instrucciones:
- Lee la fórmula de forma natural, como si la estuvieras explicando verbalmente
- NO digas letras sueltas como "e igual m c dos"
- Di nombres completos: "E igual a m por c al cuadrado"
- Para exponentes usa "al cuadrado", "al cubo", "elevado a la potencia"
- Para fracciones usa "dividido por" o "sobre"
- Para raíces usa "raíz cuadrada de", "raíz cúbica de"
- Para símbolos griegos usa su nombre: "alpha", "beta", "delta", "sigma"
- Para sumas usa "suma de"
- Para integrales usa "integral de"

Ejemplos:
- E igual mc al cuadrado se lee como "E igual a m por c al cuadrado"
- La fórmula cuadrática se lee como "x igual a menos b más menos raíz cuadrada de b al cuadrado menos cuatro a c, todo dividido por dos a"
- Una integral se lee como "integral desde cero hasta infinito de e elevado a menos x, de equis"

Fórmula a convertir:
{texto}

Responde SOLO con la lectura en lenguaje natural, sin explicaciones adicionales.
"""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content

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
    # Inicializar variables de sesión para navegación
    if "bloques_audio" not in st.session_state:
        st.session_state.bloques_audio = []
        st.session_state.indice_actual = 0
        st.session_state.indice_audio_bloque = 0
        st.session_state.notebook_cargado = False
    
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
                    
                    # Para fórmulas, convertir a lenguaje natural antes de generar audio
                    if tipo == "formula":
                        contenido_legible = leer_formula_correctamente(cell_source)
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
        st.session_state.indice_actual = 0  # Iniciar desde el primer bloque
        st.session_state.indice_audio_bloque = 0  # Iniciar desde el primer audio
        st.session_state.notebook_cargado = True
        st.success(f"✅ Notebook procesado: {len(bloques)} bloques encontrados")
    
    # Mostrar bloque actual
    if st.session_state.bloques_audio:
        # Inicializar índice de audio dentro del bloque
        if "indice_audio_bloque" not in st.session_state:
            st.session_state.indice_audio_bloque = 0
        
        indice = st.session_state.indice_actual
        total_bloques = len(st.session_state.bloques_audio)
        
        bloque_actual = st.session_state.bloques_audio[indice]
        total_audios_bloque = len(bloque_actual["audios"])
        indice_audio = st.session_state.indice_audio_bloque
        
        # Asegurar que el índice de audio esté dentro de rango
        if indice_audio >= total_audios_bloque:
            indice_audio = 0
            st.session_state.indice_audio_bloque = 0
        
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
        import base64
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
                    st.session_state.indice_audio_bloque = 0  # Reiniciar al primer audio del bloque anterior
                    st.rerun()
        
        with col2:
            # Usar un key único para forzar el rerun
            if st.button("🔄 Reiniciar", use_container_width=True, key=f"btn_reiniciar_{st.session_state.indice_actual}_{st.session_state.indice_audio_bloque}"):
                st.session_state.indice_audio_bloque = 0  # Reiniciar al primer audio del bloque actual
                st.rerun()
        
        with col3:
            if st.button("⏭️ Siguiente", use_container_width=True, key="btn_siguiente"):
                # Si hay más audios en el bloque actual, avanzar al siguiente audio
                if st.session_state.indice_audio_bloque < total_audios_bloque - 1:
                    st.session_state.indice_audio_bloque += 1
                    st.rerun()
                # Si no, avanzar al siguiente bloque
                elif st.session_state.indice_actual < total_bloques - 1:
                    st.session_state.indice_actual += 1
                    st.session_state.indice_audio_bloque = 0
                    st.rerun()
                else:
                    # Llegamos al final - generar y reproducir audio de despedida
                    texto_final = "Has llegado al final del documento"
                    audio_final = text_to_speech(texto_final)
                    st.info("✅ " + texto_final)
                    st.audio(audio_final, format="audio/mp3", autoplay=True)
        
        # JavaScript para manejar hover
        st.markdown("""
        <script>
        (function() {
            function initHover() {
                const hoverAnterior = document.getElementById('hoverAnterior');
                const hoverSiguiente = document.getElementById('hoverSiguiente');
                const hoverReiniciar = document.getElementById('hoverReiniciar');
                
                if (!hoverAnterior || !hoverSiguiente || !hoverReiniciar) {
                    return false;
                }
                
                const allButtons = document.querySelectorAll('button');
                let btnAnterior, btnSiguiente, btnReiniciar;
                
                allButtons.forEach(btn => {
                    const text = btn.textContent || btn.innerText || '';
                    if (text.includes('Anterior')) btnAnterior = btn;
                    else if (text.includes('Siguiente')) btnSiguiente = btn;
                    else if (text.includes('Reiniciar')) btnReiniciar = btn;
                });
                
                if (btnAnterior) {
                    btnAnterior.addEventListener('mouseenter', function() {
                        hoverAnterior.currentTime = 0;
                        hoverAnterior.play().catch(e => console.log('Error:', e));
                    });
                }
                
                if (btnSiguiente) {
                    btnSiguiente.addEventListener('mouseenter', function() {
                        hoverSiguiente.currentTime = 0;
                        hoverSiguiente.play().catch(e => console.log('Error:', e));
                    });
                }
                
                if (btnReiniciar) {
                    btnReiniciar.addEventListener('mouseenter', function() {
                        hoverReiniciar.currentTime = 0;
                        hoverReiniciar.play().catch(e => console.log('Error:', e));
                    });
                }
                
                return true;
            }
            
            let attempts = 0;
            const maxAttempts = 15;
            const interval = setInterval(function() {
                attempts++;
                if (initHover() || attempts >= maxAttempts) {
                    clearInterval(interval);
                }
            }, 200);
        })();
        </script>
        """, unsafe_allow_html=True)

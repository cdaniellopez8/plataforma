import streamlit as st
import nbformat
from openai import OpenAI
import re

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
        st.session_state.notebook_cargado = True
        st.success(f"✅ Notebook procesado: {len(bloques)} bloques encontrados")
    
    # Mostrar bloque actual
    if st.session_state.bloques_audio:
        indice = st.session_state.indice_actual
        total_bloques = len(st.session_state.bloques_audio)
        
        # Calcular qué audio mostrar dentro del bloque
        bloque_actual = st.session_state.bloques_audio[indice]
        
        st.markdown(f"### 📍 Bloque {bloque_actual['numero']} de {total_bloques}")
        
        # Mostrar el contenido actual
        for audio_info in bloque_actual["audios"]:
            if "texto" in audio_info:
                st.write(audio_info["texto"])
            
            st.audio(audio_info["bytes"], format="audio/mp3", autoplay=True)
            
            if audio_info["mostrar_contenido"]:
                if bloque_actual["tipo_celda"] == "code":
                    st.code(bloque_actual["contenido"], language="python")
                else:
                    st.markdown(bloque_actual["contenido"])
            
            # Solo mostrar el primer audio por ahora
            break
        
        # Botón siguiente
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("⏭️ Siguiente", use_container_width=True, key="btn_siguiente"):
                if st.session_state.indice_actual < total_bloques - 1:
                    st.session_state.indice_actual += 1
                    st.rerun()
                else:
                    st.info("✅ Has llegado al final del notebook")

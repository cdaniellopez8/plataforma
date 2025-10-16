import streamlit as st
import nbformat
from openai import OpenAI
import re
import io
import time

# -------------------------
# Configuración inicial
# -------------------------
st.set_page_config(page_title="Lector Inclusivo de Notebooks", layout="centered")
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")

# Instrucciones claras para usuario ciego
instrucciones = """
Bienvenido al lector inclusivo.  
Esta aplicación convierte notebooks de Jupyter en una experiencia auditiva accesible.

1. Sube un archivo con extensión `.ipynb`.
2. Usa los botones para moverte entre bloques:
   - **Anterior bloque** para retroceder.
   - **Pausar / Reanudar** para detener o continuar la lectura.
   - **Siguiente bloque** para avanzar al próximo fragmento.
3. Si el bloque contiene una **fórmula o tabla**, escucharás primero una descripción sencilla en español antes del contenido.
"""
st.markdown(instrucciones)

# -------------------------
# Funciones auxiliares
# -------------------------
def detectar_tipo_contenido(texto):
    """Detecta si el contenido es texto, fórmula o tabla."""
    texto = texto.strip()
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):
        return "tabla"
    else:
        return "texto"

def limpiar_texto(texto):
    """Elimina encabezados y espacios innecesarios."""
    lineas = texto.split("\n")
    lineas_limpias = [l for l in lineas if not l.strip().startswith("#")]
    return "\n".join(lineas_limpias).strip()

def describir_contenido(tipo, texto):
    """Genera descripción en español natural según tipo de bloque."""
    if tipo == "formula":
        prompt = f"""
        Eres un narrador que lee notebooks científicos a personas ciegas en español.
        Debes decir una frase breve como:
        "A continuación verás una fórmula. Esta trata sobre [tema general de la fórmula, sin símbolos ni ecuaciones]."
        NO digas símbolos, signos ni letras del alfabeto matemático.
        Contenido:
        {texto[:700]}
        """
    elif tipo == "tabla":
        prompt = f"""
        Eres un narrador que ayuda a personas ciegas.  
        Vas a describir una tabla de forma breve en español.  
        Primero di: "A continuación verás una tabla con las siguientes columnas:"  
        Luego, menciona las columnas y su tipo (numérica, texto, identificador, fecha, etc.).  
        No leas el contenido, solo describe la estructura.
        Contenido:
        {texto[:1000]}
        """
    else:
        return texto

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )
    return response.choices[0].message.content.strip()

def text_to_speech(text):
    """Convierte texto en audio (voz natural en español)."""
    audio_response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return io.BytesIO(audio_response.read())

# -------------------------
# Subida del archivo
# -------------------------
uploaded_file = st.file_uploader("📤 Sube tu notebook", type=["ipynb"])

if uploaded_file:
    notebook = nbformat.read(uploaded_file, as_version=4)
    bloques = []

    # Procesar celdas del notebook
    for cell in notebook.cells:
        if cell["cell_type"] == "markdown":
            texto = limpiar_texto(cell["source"])
            if texto:
                tipo = detectar_tipo_contenido(texto)
                bloques.append((tipo, texto))
        elif cell["cell_type"] == "code":
            texto = cell["source"].strip()
            if texto:
                bloques.append(("codigo", texto))

    # Inicializar sesión
    if "ultimo_archivo" not in st.session_state or st.session_state.ultimo_archivo != uploaded_file.name:
        st.session_state.index = 0
        st.session_state.reproduciendo = True
        st.session_state.ultimo_archivo = uploaded_file.name

    # Funciones de navegación
    def siguiente():
        if st.session_state.index < len(bloques) - 1:
            st.session_state.index += 1
            st.session_state.reproduciendo = True
            st.rerun()

    def anterior():
        if st.session_state.index > 0:
            st.session_state.index -= 1
            st.session_state.reproduciendo = True
            st.rerun()

    def toggle_pausa():
        st.session_state.reproduciendo = not st.session_state.reproduciendo
        st.rerun()

    # Mostrar bloque actual
    tipo, texto = bloques[st.session_state.index]
    texto = limpiar_texto(texto)

    st.markdown(f"### 📘 Bloque {st.session_state.index + 1} de {len(bloques)}")

    # Generar texto que se reproducirá
    if tipo in ["formula", "tabla"]:
        descripcion = describir_contenido(tipo, texto)
        texto_a_leer = descripcion + "\n\n" + texto
    elif tipo == "codigo":
        texto_a_leer = "A continuación verás un bloque de código en Python."
    else:
        texto_a_leer = texto

    # Mostrar texto o código visualmente (para oyentes con resto visual)
    if tipo == "codigo":
        st.code(texto, language="python")
    else:
        st.text_area("Contenido del bloque", texto, height=200)

    # Controles de navegación
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("⏮️ Anterior", on_click=anterior, use_container_width=True)
    with col2:
        estado = "⏸️ Pausar" if st.session_state.reproduciendo else "▶️ Reanudar"
        st.button(estado, on_click=toggle_pausa, use_container_width=True)
    with col3:
        st.button("⏭️ Siguiente", on_click=siguiente, use_container_width=True)

    # Reproducción automática
    if st.session_state.reproduciendo:
        audio = text_to_speech(texto_a_leer)
        st.audio(audio, format="audio/mp3", start_time=0)

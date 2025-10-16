import streamlit as st
import nbformat
from openai import OpenAI
import re
import base64

# ---------------- Config ----------------
st.set_page_config(page_title="Lector Inclusivo (.ipynb)", layout="centered")
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------------- Helpers ----------------
def detectar_tipo_contenido(texto):
    if re.search(r"\$.*\$|\\begin\{equation\}", texto):
        return "formula"
    elif re.search(r"\|.+\|", texto) or re.search(r"---", texto):
        return "tabla"
    else:
        return "texto"

def limpiar_texto(texto):
    lines = texto.splitlines()
    lines = [re.sub(r"^[#>\-\*\s]+", "", l).strip() for l in lines]
    lines = [l for l in lines if l]
    return " ".join(lines).strip()

def describir_contenido(tipo, texto):
    if tipo == "formula":
        prompt = (
            "Eres un narrador en español que prepara una frase breve para personas ciegas.\n"
            "Devuelve exactamente una frase con este formato:\n"
            "\"A continuación verás una fórmula. Esta trata sobre [breve descripción sin símbolos ni fórmulas].\"\n"
            f"Contenido de ejemplo: {texto[:700]}"
        )
    elif tipo == "tabla":
        prompt = (
            "Eres un narrador en español que describe tablas para personas ciegas.\n"
            "Primera línea EXACTA: \"A continuación verás una tabla con las siguientes columnas:\"\n"
            "Luego, lista cada columna en formato: '- columna <nombre>, tipo <numérica/texto/identificador/fecha>'\n"
            f"Contenido de ejemplo: {texto[:1000]}"
        )
    elif tipo == "codigo":
        prompt = (
            "Eres un narrador en español. Describe brevemente qué hace este bloque de código sin leerlo.\n"
            f"Contenido de ejemplo: {texto[:1000]}"
        )
    else:
        return texto

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content": prompt}],
        temperature=0.2
    )
    return resp.choices[0].message.content.strip()

def text_to_bytes_audio(text):
    audio_resp = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return audio_resp.read()

def bytes_to_data_uri(mp3_bytes):
    b64 = base64.b64encode(mp3_bytes).decode("utf-8")
    return f"data:audio/mp3;base64,{b64}"

# ---------------- Instrucciones (solo una vez) ----------------
if "instrucciones_leidas" not in st.session_state:
    instrucciones_texto = (
        "Bienvenido al lector inclusivo de notebooks. "
        "Solo hay un botón grande: presiona una vez para pausar o reanudar, "
        "presiona dos veces seguidas para pasar al siguiente bloque. "
        "Si pasas el cursor sobre el botón escucharás esta ayuda."
    )
    instr_bytes = text_to_bytes_audio(instrucciones_texto)
    instr_uri = bytes_to_data_uri(instr_bytes)
    st.session_state.instrucciones_audio = instr_uri
    st.session_state.instrucciones_leidas = False

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")
st.markdown("**Instrucciones (texto y audio):**")
st.write(
    "Presiona una vez el botón para pausar o reanudar, dos veces para pasar al siguiente bloque."
)

if not st.session_state.instrucciones_leidas:
    st.markdown(f"""
    <audio id="instrAudio" autoplay>
      <source src="{st.session_state.instrucciones_audio}" type="audio/mp3">
    </audio>
    """, unsafe_allow_html=True)
    st.session_state.instrucciones_leidas = True

# ---------------- File upload ----------------
uploaded = st.file_uploader("📤 Sube tu archivo .ipynb", type=["ipynb"])
if uploaded is None:
    st.stop()

# ---------------- Process notebook ----------------
nb = nbformat.read(uploaded, as_version=4)
cells = [c for c in nb.cells if c.get("source","").strip()]
if not cells:
    st.error("No se encontraron celdas con contenido.")
    st.stop()

# ---------- initialize state ----------
if "index" not in st.session_state or st.session_state.get("last_file") != uploaded.name:
    st.session_state.index = 0
    st.session_state.last_file = uploaded.name

# ---------- check query params ----------
params = st.query_params
if "action" in params and params["action"] == "next":
    if st.session_state.index < len(cells)-1:
        st.session_state.index += 1
    st.query_params.clear()  # limpia la URL
    st.rerun()

# ---------- prepare current block ----------
i = st.session_state.index
cell = cells[i]
raw = cell.get("source","")
tipo = detectar_tipo_contenido(raw)
texto_limpio = limpiar_texto(raw)

if cell.get("cell_type") == "code":
    intro = describir_contenido("codigo", raw)
    texto_a_leer = intro
else:
    if tipo in ["formula","tabla"]:
        intro = describir_contenido(tipo, raw)
        texto_a_leer = (intro + "\n\n" + texto_limpio) if intro else texto_limpio
    else:
        texto_a_leer = texto_limpio

# generate audio
audio_bytes = text_to_bytes_audio(texto_a_leer)
audio_uri = bytes_to_data_uri(audio_bytes)

hover_help_bytes = text_to_bytes_audio(
    "Botón de reproducción. Un clic pausa o reanuda. Doble clic pasa al siguiente bloque."
)
hover_help_uri = bytes_to_data_uri(hover_help_bytes)

# ---------- display UI ----------
st.markdown(f"### Bloque {i+1} / {len(cells)} — tipo: {tipo}")
if cell.get("cell_type") == "code":
    st.code(raw, language="python")
else:
    st.text_area("Vista previa del contenido", texto_limpio, height=150)

html = f"""
<style>
  #bigBtn {{
    width: 100%;
    height: 140px;
    font-size: 28px;
    background-color: #1f77b4;
    color: white;
    border: none;
    border-radius: 12px;
  }}
</style>

<audio id="player" preload="auto">
  <source src="{audio_uri}" type="audio/mp3">
</audio>

<audio id="hoverHelp" preload="auto">
  <source src="{hover_help_uri}" type="audio/mp3">
</audio>

<button id="bigBtn">🎵 Pulsar una vez: pausa/reanuda • Doble pulsar: siguiente</button>

<script>
  const btn = document.getElementById('bigBtn');
  const player = document.getElementById('player');
  const hover = document.getElementById('hoverHelp');

  // Autoplay intento
  try {{ player.play().catch(()=>{{}}); }} catch(e){{}}

  btn.addEventListener('mouseenter', () => {{
    try {{ hover.currentTime = 0; hover.play().catch(()=>{{}}); }} catch(e){{}}
  }});

  btn.addEventListener('click', () => {{
    if (player.paused) player.play().catch(()=>{{}});
    else player.pause();
  }});

  btn.addEventListener('dblclick', () => {{
    const url = new URL(window.location);
    url.searchParams.set('action', 'next');
    url.searchParams.set('t', Date.now());
    window.location.href = url.toString();
  }});
</script>
"""

st.components.v1.html(html, height=230, scrolling=False)

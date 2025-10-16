import streamlit as st
import nbformat
from openai import OpenAI
import re
import base64
import io

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
        prompt = f"""
Eres un narrador en español que prepara una frase breve para personas ciegas.
Devuelve exactamente una frase con este formato:
"A continuación verás una fórmula. Esta trata sobre [breve descripción sin símbolos ni fórmulas]."
No repitas la fórmula, no digas símbolos.
Contenido de ejemplo (útil para inferir, NO repetir): {texto[:700]}
"""
    elif tipo == "tabla":
        prompt = f"""
Eres un narrador en español que describe tablas para personas ciegas.
Primera línea EXACTA: "A continuación verás una tabla con las siguientes columnas:"
Luego, lista cada columna en formato: "- columna <nombre>, tipo <numérica/texto/identificador/fecha>"
Si puedes, indica cuántas filas aproximadamente.
Contenido de ejemplo (útil para inferir columnas): {texto[:1200]}
"""
    else:
        return texto

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content": prompt}],
        temperature=0.2
    )
    return resp.choices[0].message.content.strip()

def text_to_bytes_audio(text):
    """Genera audio (MP3 bytes) usando audio.speech.create y devuelve bytes."""
    audio_resp = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    return audio_resp.read()

def bytes_to_data_uri(mp3_bytes):
    b64 = base64.b64encode(mp3_bytes).decode("utf-8")
    return f"data:audio/mp3;base64,{b64}"

# ---------------- Instrucciones iniciales ----------------
instrucciones_texto = (
    "Bienvenido al lector inclusivo de notebooks. "
    "Solo hay un botón grande: presiona una vez para pausar o reanudar, "
    "presiona dos veces seguidas para pasar al siguiente bloque. "
    "Si pasas el cursor sobre el botón escucharás esta ayuda."
)
# pre-generate audio for hover/instructions (small cost)
instr_bytes = text_to_bytes_audio(instrucciones_texto)
instr_uri = bytes_to_data_uri(instr_bytes)

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")
st.markdown("**Instrucciones (texto y audio):**")
st.write(instrucciones_texto)

# renderear el audio de instrucciones (autoplay una sola vez mediante HTML)
st.markdown(f"""
<audio id="instrAudio" preload="auto">
  <source src="{instr_uri}" type="audio/mp3">
</audio>
<script>
  // reproducir una vez al cargar (pero algunos navegadores bloquean autoplay con sonido)
  try {{
    var a = document.getElementById('instrAudio');
    a.play().catch(()=>{{}});
  }} catch(e){{}}
</script>
""", unsafe_allow_html=True)

# ---------------- File upload ----------------
uploaded = st.file_uploader("📤 Sube tu archivo .ipynb", type=["ipynb"])

if uploaded is None:
    st.stop()

# ---------------- Procesar notebook ----------------
nb = nbformat.read(uploaded, as_version=4)
cells = [c for c in nb.cells if c.get("source","").strip()]
if not cells:
    st.error("No se encontraron celdas con contenido en el notebook.")
    st.stop()

# ---------------- State init ----------------
if "index" not in st.session_state or st.session_state.get("last_file") != uploaded.name:
    st.session_state.index = 0
    st.session_state.last_file = uploaded.name

# ---------------- Detect action from query params ----------------
params = st.experimental_get_query_params()
# Si URL tiene ?action=next -> avanzar
if "action" in params and params["action"][0] == "next":
    # avanzar (si es posible)
    if st.session_state.index < len(cells)-1:
        st.session_state.index += 1
    # limpiar parámetros para evitar bucles
    st.experimental_set_query_params()
    # rerun para que se procese el nuevo índice
    st.experimental_rerun()

# ---------------- Preparar texto a reproducir para el bloque actual ----------------
i = st.session_state.index
cell = cells[i]
raw = cell.get("source","")
tipo = detectar_tipo_contenido(raw)
texto_limpio = limpiar_texto(raw)

if cell.get("cell_type") == "code":
    intro = describir_contenido("codigo", raw)  # breve explicación del código
    # construimos un texto final: intro (si existe) + aviso + no leer el código literal
    texto_a_leer = intro or "A continuación verás un bloque de código."
else:
    if tipo in ["formula","tabla"]:
        intro = describir_contenido(tipo, raw)
        # leer intro (explicación) y luego el contenido (para tablas leemos la estructura si es necesario)
        texto_a_leer = (intro + "\n\n" + texto_limpio) if intro else texto_limpio
    else:
        texto_a_leer = texto_limpio

# generar audio bytes y data URI (se puede cachear en estado si se desea)
audio_bytes = text_to_bytes_audio(texto_a_leer)
audio_uri = bytes_to_data_uri(audio_bytes)

# hover help audio
hover_help_bytes = text_to_bytes_audio("Botón de reproducción. Un clic pausa o reanuda. Doble clic pasa al siguiente bloque.")
hover_help_uri = bytes_to_data_uri(hover_help_bytes)

# ---------------- Mostrar info y reproducir con HTML controlable por JS ----------------
st.markdown(f"### Bloque {i+1} / {len(cells)} — tipo: {tipo}")
# mostrar preview del texto (útil para quien pueda verlo)
if cell.get("cell_type") == "code":
    st.code(raw, language="python")
else:
    st.text_area("Vista previa del contenido", texto_limpio, height=160)

# Construimos HTML + JS:
# - <audio id="player"> con src = audio_uri
# - Un botón grande que:
#    * en 'mouseenter' reproduce hover_help audio
#    * en 'click' alterna play/pause
#    * en 'dblclick' modifica window.location.search ?action=next&ts=... provocando recarga
# Nota: usar dblclick nativo y asegurar que click simple no interfiera.
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
  #bigBtn:active {{ transform: translateY(1px); }}
</style>

<audio id="player" preload="auto">
  <source src="{audio_uri}" type="audio/mp3">
  Your browser does not support the audio element.
</audio>

<audio id="hoverHelp" preload="auto">
  <source src="{hover_help_uri}" type="audio/mp3">
</audio>

<button id="bigBtn" aria-label="Botón único de control">🎵 Pulsar: pausa / doble pulsar: siguiente</button>

<script>
  const player = document.getElementById('player');
  const btn = document.getElementById('bigBtn');
  const hover = document.getElementById('hoverHelp');

  // autoplay cuando la página carga (al recargar por action=next también)
  try {{
    player.currentTime = 0;
    player.play().catch(()=>{{}}); // algunos navegadores bloquean autoplay con sonido
  }} catch(e){{}}

  // hover ayuda
  btn.addEventListener('mouseenter', () => {{
    try {{ hover.currentTime = 0; hover.play().catch(()=>{{}}); }} catch(e){{}}
  }});

  // single click toggle play/pause
  btn.addEventListener('click', (e) => {{
    // si el doble click ocurre, el dblclick handler se ejecutará inmediatamente después,
    // pero click también se ejecuta. Para evitar conflicto, no retrasamos acá; en práctica
    // dblclick hará redirección antes de que el usuario note la pausa.
    if (player.paused) {{
      player.play().catch(()=>{{}});
    }} else {{
      player.pause();
    }}
  }});

  // dblclick -> cambiar query param para indicar siguiente bloque
  btn.addEventListener('dblclick', (e) => {{
    // construir nueva query con action=next y timestamp para evitar cache
    const url = new URL(window.location);
    url.searchParams.set('action', 'next');
    url.searchParams.set('ts', Date.now());
    window.location.href = url.toString();
  }});
</script>
"""

st.markdown(html, unsafe_allow_html=True)

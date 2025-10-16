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
        prompt = (
            "Eres un narrador en español que prepara una frase breve para personas ciegas.\n"
            "Devuelve exactamente una frase con este formato:\n"
            "\"A continuación verás una fórmula. Esta trata sobre [breve descripción sin símbolos ni fórmulas].\"\n"
            "No repitas la fórmula ni leas símbolos.\n"
            f"Contenido de ejemplo: {texto[:700]}"
        )
    elif tipo == "tabla":
        prompt = (
            "Eres un narrador en español que describe tablas para personas ciegas.\n"
            "Primera línea EXACTA: \"A continuación verás una tabla con las siguientes columnas:\"\n"
            "Luego, lista cada columna en formato: '- columna <nombre>, tipo <numérica/texto/identificador/fecha>'\n"
            f"Contenido de ejemplo: {texto[:1200]}"
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

# ---------------- Instrucciones iniciales (solo una vez) ----------------
if "welcome_played" not in st.session_state:
    instr_txt = (
        "Bienvenido al lector inclusivo. "
        "Hay tres botones grandes: anterior, pausa o reanudar, y siguiente. "
        "Al pasar el cursor sobre un botón escucharás su descripción. "
        "Usa Siguiente para avanzar al siguiente bloque."
    )
    instr_bytes = text_to_bytes_audio(instr_txt)
    st.session_state.welcome_audio_uri = bytes_to_data_uri(instr_bytes)
    st.session_state.welcome_played = False

# ---------------- UI header ----------------
st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")
st.markdown("**Instrucciones (texto + audio inicial):**")
st.write("Sube un `.ipynb`. Usa los botones grandes: Anterior / Pausa-Reanudar / Siguiente.")

# reproducir la instrucción una sola vez al cargar la app (no en cada navegación)
if not st.session_state.welcome_played:
    st.markdown(f"""
    <audio id="welcome" preload="auto" autoplay>
      <source src="{st.session_state.welcome_audio_uri}" type="audio/mp3">
    </audio>
    """, unsafe_allow_html=True)
    st.session_state.welcome_played = True

# ---------------- File upload ----------------
uploaded = st.file_uploader("📤 Sube tu archivo .ipynb", type=["ipynb"])
if uploaded is None:
    st.stop()

# ---------------- Procesar notebook ----------------
nb = nbformat.read(uploaded, as_version=4)
cells = [c for c in nb.cells if c.get("source","").strip()]
if not cells:
    st.error("No se encontraron celdas con contenido.")
    st.stop()

# initialize state for new file
if st.session_state.get("last_file") != uploaded.name:
    st.session_state.last_file = uploaded.name
    st.session_state.index = 0
    st.session_state.play = True  # autoplay attempt on load
    st.session_state.audio_uris = [None] * len(cells)
    st.session_state.hover_uris = {}
    # We will cache hover audios per button label

# ----------------- Prepare hover audios (cached) -----------------
def get_hover_uri(label):
    # label: "prev", "main", "next" etc.
    if label in st.session_state.hover_uris:
        return st.session_state.hover_uris[label]
    txts = {
        "prev": "Botón anterior. Vuelve al bloque anterior.",
        "main": "Botón principal. Un clic pausa o reanuda. Para avanzar use el botón siguiente.",
        "next": "Botón siguiente. Avanza al siguiente bloque y lo reproduce."
    }
    b = text_to_bytes_audio(txts[label])
    uri = bytes_to_data_uri(b)
    st.session_state.hover_uris[label] = uri
    return uri

# ----------------- Prepare main audio for an index (cache) -----------------
def ensure_audio_for_index(i):
    if st.session_state.audio_uris[i] is not None:
        return st.session_state.audio_uris[i]
    cell = cells[i]
    raw = cell.get("source","")
    tipo = detectar_tipo_contenido(raw) if cell.get("cell_type") != "code" else "codigo"
    texto = limpiar_texto(raw)
    if cell.get("cell_type") == "code":
        intro = describir_contenido("codigo", raw)
        texto_a_leer = intro or "A continuación verás un bloque de código."
    else:
        if tipo in ["formula","tabla"]:
            intro = describir_contenido(tipo, raw)
            texto_a_leer = (intro + "\n\n" + texto) if intro else texto
        else:
            texto_a_leer = texto
    bytes_audio = text_to_bytes_audio(texto_a_leer)
    uri = bytes_to_data_uri(bytes_audio)
    st.session_state.audio_uris[i] = uri
    return uri

# Ensure current index audio exists
current_idx = st.session_state.index
ensure_audio_for_index(current_idx)

# ----------------- Display info and audio element (controlled by JS) -----------------
cell = cells[current_idx]
raw = cell.get("source","")
tipo = detectar_tipo_contenido(raw) if cell.get("cell_type") != "code" else "codigo"
texto_limpio = limpiar_texto(raw)

st.markdown(f"### Bloque {current_idx+1} / {len(cells)} — tipo: {tipo}")
if cell.get("cell_type") == "code":
    st.code(raw, language="python")
else:
    st.text_area("Vista previa del contenido", texto_limpio, height=160)

# Audio URIs
main_audio_uri = st.session_state.audio_uris[current_idx]
hover_prev_uri = get_hover_uri("prev")
hover_main_uri = get_hover_uri("main")
hover_next_uri = get_hover_uri("next")

# HTML + JS:
# - player audio element (id=player)
# - hover audios (hoverPrev/hoverMain/hoverNext)
# - buttons: Prev (streamlit), Main (streamlit), Next (streamlit)
# We'll use Streamlit buttons for navigation to ensure server increments index reliably.
# But we still attach JS to the player to pause/resume when hover plays.
html = f"""
<audio id="player" preload="auto" {'autoplay' if st.session_state.play else ''}>
  <source src="{main_audio_uri}" type="audio/mp3">
</audio>

<audio id="hoverPrev" preload="auto"><source src="{hover_prev_uri}" type="audio/mp3"></audio>
<audio id="hoverMain" preload="auto"><source src="{hover_main_uri}" type="audio/mp3"></audio>
<audio id="hoverNext" preload="auto"><source src="{hover_next_uri}" type="audio/mp3"></audio>

<script>
  const player = document.getElementById('player');
  const hoverPrev = document.getElementById('hoverPrev');
  const hoverMain = document.getElementById('hoverMain');
  const hoverNext = document.getElementById('hoverNext');

  // helper to play hover audio without overlap:
  function playHover(hoverAudio) {{
    try {{
      // stop other hover audios
      [hoverPrev, hoverMain, hoverNext].forEach(a => {{
        if (a !== hoverAudio) {{ a.pause(); a.currentTime = 0; }}
      }});
      // if player is playing, remember and pause it
      const wasPlaying = !player.paused;
      if (wasPlaying) {{
        player.pause();
      }}
      // play hover
      hoverAudio.currentTime = 0;
      hoverAudio.play().catch(()=>{{}});
      // when hover ends, resume player if wasPlaying
      hoverAudio.onended = () => {{
        try {{
          if (wasPlaying) {{
            player.play().catch(()=>{{}});
          }}
        }} catch(e){{ console.log(e); }}
      }};
    }} catch(e){{ console.log(e); }}
  }}

  // Prevent overlapping: when player starts, stop any hover
  [hoverPrev, hoverMain, hoverNext].forEach(a => {{
    a.addEventListener('play', () => {{
      try {{ [hoverPrev, hoverMain, hoverNext].forEach(x=>{{ if (x!==a) {{ x.pause(); x.currentTime=0; }} }}); }} catch(e){{}}
    }});
  }});

  // expose function for external use (if needed)
  window.playHover = playHover;
</script>
"""

st.components.v1.html(html, height=1, scrolling=False)  # render invisible audio elements

# ----------------- Controls (Streamlit buttons, large) -----------------
st.markdown("---")
col1, col2, col3 = st.columns([1,1.2,1])

with col1:
    if st.button("⏮️ Anterior", key="prev", help="Vuelve al bloque anterior"):
        if st.session_state.index > 0:
            st.session_state.index -= 1
            st.session_state.play = True
            ensure_audio_for_index(st.session_state.index)
            st.experimental_rerun()

with col2:
    # big central pause/resume button
    label = "⏯️ Pausa/Reanuda"
    if st.button(label, key="play_pause", help="Un clic pausa o reanuda el audio actual"):
        # toggle play flag; when True, audio element renders with autoplay
        st.session_state.play = not st.session_state.play
        st.experimental_rerun()

with col3:
    if st.button("⏭️ Siguiente", key="next_btn", help="Avanza al siguiente bloque"):
        if st.session_state.index < len(cells) - 1:
            st.session_state.index += 1
            st.session_state.play = True
            ensure_audio_for_index(st.session_state.index)
            st.experimental_rerun()

# ----------------- Attach hover JS behavior to the Streamlit rendered buttons -----------------
# We add small inline JS that finds the Streamlit buttons by text and attaches mouseenter
attach_js = f"""
<script>
function findButtonByText(text) {{
  // find buttons rendered by Streamlit (they are <button> elements); choose the one with innerText containing text
  let btns = Array.from(document.querySelectorAll("button"));
  for (let b of btns) {{
    if (b.innerText && b.innerText.includes(text)) return b;
  }}
  return null;
}}

function setup() {{
  const prevBtn = findButtonByText("⏮️ Anterior");
  const mainBtn = findButtonByText("⏯️ Pausa/Reanuda");
  const nextBtn = findButtonByText("⏭️ Siguiente");
  const hoverPrev = document.getElementById('hoverPrev');
  const hoverMain = document.getElementById('hoverMain');
  const hoverNext = document.getElementById('hoverNext');
  const player = document.getElementById('player');

  if (prevBtn) {{
    prevBtn.addEventListener('mouseenter', () => {{ window.playHover(hoverPrev); }});
  }}
  if (mainBtn) {{
    mainBtn.addEventListener('mouseenter', () => {{ window.playHover(hoverMain); }});
  }}
  if (nextBtn) {{
    nextBtn.addEventListener('mouseenter', () => {{ window.playHover(hoverNext); }});
  }}

  // ensure hover audios don't play more than once per hover: handled by browser naturally
}}

setTimeout(setup, 800); // allow Streamlit to render buttons
</script>
"""
st.components.v1.html(attach_js, height=0, scrolling=False)

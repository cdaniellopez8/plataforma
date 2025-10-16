import streamlit as st
import nbformat
from openai import OpenAI
import re
import base64

st.set_page_config(page_title="Lector Inclusivo de Notebooks (.ipynb)", layout="centered")
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------------- Funciones auxiliares ----------------
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
            "Eres un narrador en español para personas ciegas. "
            "Di solo una frase del tipo: "
            "\"A continuación verás una fórmula. Esta trata sobre [breve descripción sin símbolos]\". "
            f"Contenido: {texto[:800]}"
        )
    elif tipo == "tabla":
        prompt = (
            "Eres un narrador en español para personas ciegas. "
            "Di: \"A continuación verás una tabla con las siguientes columnas:\" "
            "y luego lista cada columna con su tipo inferido (numérica, texto, identificador, fecha). "
            f"Contenido: {texto[:1000]}"
        )
    elif tipo == "codigo":
        prompt = (
            "Eres un narrador en español para personas ciegas. "
            "Di una frase corta explicando qué hace este bloque de código, sin leer el código. "
            f"Contenido: {texto[:1000]}"
        )
    else:
        return texto

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
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

# ---------------- Instrucciones iniciales ----------------
if "instrucciones_leidas" not in st.session_state:
    instrucciones_texto = (
        "Bienvenido al lector inclusivo de notebooks. "
        "Hay tres botones grandes. "
        "El del centro pausa o reanuda con un clic, y avanza al siguiente con doble clic. "
        "El de la izquierda va al bloque anterior. "
        "El de la derecha reinicia el audio actual. "
        "Si pasas el cursor sobre un botón, escucharás su descripción."
    )
    instr_bytes = text_to_bytes_audio(instrucciones_texto)
    st.session_state.instrucciones_audio = bytes_to_data_uri(instr_bytes)
    st.session_state.instrucciones_leidas = False

st.title("🎧 Lector Inclusivo de Notebooks (.ipynb)")

if not st.session_state.instrucciones_leidas:
    st.markdown(f"""
    <audio autoplay>
      <source src="{st.session_state.instrucciones_audio}" type="audio/mp3">
    </audio>
    """, unsafe_allow_html=True)
    st.session_state.instrucciones_leidas = True

# ---------------- Subida del archivo ----------------
uploaded = st.file_uploader("📤 Sube tu archivo .ipynb", type=["ipynb"])
if uploaded is None:
    st.stop()

# ---------------- Procesar el notebook ----------------
nb = nbformat.read(uploaded, as_version=4)
cells = [c for c in nb.cells if c.get("source", "").strip()]
if not cells:
    st.error("No se encontraron celdas con contenido.")
    st.stop()

# ---------- Estado ----------
if "index" not in st.session_state or st.session_state.get("last_file") != uploaded.name:
    st.session_state.index = 0
    st.session_state.last_file = uploaded.name

params = st.query_params
action = params.get("action", [""])[0] if isinstance(params.get("action"), list) else params.get("action", "")

if action == "next" and st.session_state.index < len(cells) - 1:
    st.session_state.index += 1
elif action == "prev" and st.session_state.index > 0:
    st.session_state.index -= 1
elif action == "restart":
    pass  # solo reinicia el audio
st.query_params.clear()

# ---------- Preparar bloque ----------
i = st.session_state.index
cell = cells[i]
raw = cell["source"]
tipo = detectar_tipo_contenido(raw)
texto = limpiar_texto(raw)

if cell["cell_type"] == "code":
    intro = describir_contenido("codigo", raw)
    texto_a_leer = intro
else:
    if tipo in ["formula", "tabla"]:
        intro = describir_contenido(tipo, raw)
        texto_a_leer = intro + "\n\n" + texto
    else:
        texto_a_leer = texto

# Generar audio
audio_bytes = text_to_bytes_audio(texto_a_leer)
audio_uri = bytes_to_data_uri(audio_bytes)

# Audios hover
hover_prev = bytes_to_data_uri(text_to_bytes_audio("Botón anterior, vuelve al bloque anterior."))
hover_center = bytes_to_data_uri(text_to_bytes_audio("Botón principal. Un clic pausa o reanuda, doble clic pasa al siguiente bloque."))
hover_restart = bytes_to_data_uri(text_to_bytes_audio("Botón reiniciar, vuelve a reproducir el audio actual desde el comienzo."))

# ---------- Interfaz ----------
st.markdown(f"### 🔹 Bloque {i+1} de {len(cells)} — tipo: {tipo}")
if cell["cell_type"] == "code":
    st.code(raw, language="python")
else:
    st.text_area("Vista previa del contenido", texto, height=150)

html = f"""
<style>
  .btn {{
    width: 32%;
    height: 130px;
    font-size: 22px;
    color: white;
    border: none;
    border-radius: 12px;
    margin: 5px;
  }}
  #prevBtn {{ background-color: #2E8B57; }}
  #mainBtn {{ background-color: #1f77b4; }}
  #restartBtn {{ background-color: #B22222; }}
  .btn:hover {{ opacity: 0.8; }}
</style>

<audio id="player" preload="auto">
  <source src="{audio_uri}" type="audio/mp3">
</audio>

<audio id="hoverPrev"><source src="{hover_prev}" type="audio/mp3"></audio>
<audio id="hoverMain"><source src="{hover_center}" type="audio/mp3"></audio>
<audio id="hoverRestart"><source src="{hover_restart}" type="audio/mp3"></audio>

<div style="display:flex; justify-content:space-between;">
  <button class="btn" id="prevBtn">⏮ Anterior</button>
  <button class="btn" id="mainBtn">🎵 Reproducir / Siguiente</button>
  <button class="btn" id="restartBtn">🔁 Reiniciar</button>
</div>

<script>
  const player = document.getElementById('player');
  const prevBtn = document.getElementById('prevBtn');
  const mainBtn = document.getElementById('mainBtn');
  const restartBtn = document.getElementById('restartBtn');
  const hoverPrev = document.getElementById('hoverPrev');
  const hoverMain = document.getElementById('hoverMain');
  const hoverRestart = document.getElementById('hoverRestart');

  function navigate(action) {{
    const url = new URL(window.location);
    url.searchParams.set('action', action);
    url.searchParams.set('t', Date.now());
    window.location.href = url.toString();
  }}

  // hover help
  prevBtn.addEventListener('mouseenter', () => {{ hoverPrev.currentTime = 0; hoverPrev.play().catch(()=>{{}}); }});
  mainBtn.addEventListener('mouseenter', () => {{ hoverMain.currentTime = 0; hoverMain.play().catch(()=>{{}}); }});
  restartBtn.addEventListener('mouseenter', () => {{ hoverRestart.currentTime = 0; hoverRestart.play().catch(()=>{{}}); }});

  // click actions
  prevBtn.addEventListener('click', () => navigate('prev'));
  restartBtn.addEventListener('click', () => navigate('restart'));

  let clickTimeout;
  mainBtn.addEventListener('click', () => {{
    if (clickTimeout) {{
      clearTimeout(clickTimeout);
      navigate('next'); // doble clic
    }} else {{
      clickTimeout = setTimeout(() => {{
        clickTimeout = null;
        if (player.paused) player.play().catch(()=>{{}});
        else player.pause();
      }}, 250);
    }}
  }});

  // Autoplay intento
  try {{ player.play().catch(()=>{{}}); }} catch(e){{}}
</script>
"""

st.components.v1.html(html, height=260, scrolling=False)

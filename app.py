import streamlit as st
import google.generativeai as genai
import sqlite3
import uuid
from PIL import Image
import time

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(
    page_title="Asistent Artizan Tradițional",
    page_icon="🎨",
    layout="centered"
)

# --- CSS PENTRU STILIZARE ---
st.markdown("""
<style>
    .stChatMessage {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 10px;
    }
    .stButton button {
        background-color: #ff4b4b;
        color: white;
    }
    .status-log {
        font-size: 0.8em;
        color: #666;
        border-left: 2px solid #ddd;
        padding-left: 10px;
        margin-bottom: 5px;
    }
    .key-expired {
        color: #d9534f;
        font-weight: bold;
    }
    .key-success {
        color: #5cb85c;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- INIȚIALIZARE SESSION STATE ---
if "user_api_key" not in st.session_state:
    st.session_state.user_api_key = ""
if "api_error" not in st.session_state:
    st.session_state.api_error = False
if "key_logs" not in st.session_state:
    st.session_state.key_logs = []

# --- PROMPT-UL DE SISTEM (PERSONALITATEA AI) ---
SYSTEM_PROMPT = """
Ești un expert în artă populară românească, tradiții, folclor și marketing pentru produse handmade.
Rolul tău este să ajuți un artist să creeze produse autentice (mărțișoare, cadouri de Crăciun, Paște).
1. Analizează pozele încărcate din punct de vedere estetic și al materialelor.
2. Sugerează îmbunătățiri cromatice sau materiale naturale (lemn, lână, lut) specifice sezonului.
3. Creează o poveste lungă, emoționantă, cu iz arhaic românesc pentru fiecare produs, pe care artistul să o pună pe etichetă sau pe social media.
Tonul trebuie să fie cald, încurajator și respectuos față de tradiție.
"""

# --- GESTIONARE CHEI API (ROTAȚIE & LOGGING) ---
def get_system_api_keys():
    try:
        keys = st.secrets["GOOGLE_API_KEYS"]
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        elif isinstance(keys, list):
            return keys
        return []
    except:
        return []

def call_gemini_with_rotation(inputs):
    """
    Încearcă cheile pe rând și returnează un log detaliat al erorilor.
    """
    logs = [] # Lista de mesaje de stare
    
    # 1. Lista de chei (User Key + System Keys)
    candidates = []
    
    if st.session_state.user_api_key:
        candidates.append(("Cheia Ta Manuală", st.session_state.user_api_key))
    
    system_keys = get_system_api_keys()
    for i, k in enumerate(system_keys):
        candidates.append((f"Cheia Server #{i+1}", k))

    if not candidates:
        return None, ["Nu există chei configurate."]

    last_error_msg = ""

    # 2. Bucla de încercare
    for source_name, key in candidates:
        try:
            genai.configure(api_key=key)
            # Folosim gemini-2.5-flash
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # Testăm generarea
            response = model.generate_content(inputs)
            
            # Dacă ajungem aici, e succes
            logs.append(f"✅ {source_name}: FUNCȚIONALĂ")
            return response.text, logs

        except Exception as e:
            error_str = str(e)
            status_msg = ""
            
            # Detectăm tipul erorii
            if "API key not valid" in error_str or "400" in error_str:
                status_msg = f"❌ {source_name}: INVALIDĂ / EXPIRATĂ"
            elif "429" in error_str or "Resource has been exhausted" in error_str:
                status_msg = f"⚠️ {source_name}: LIMITĂ ATINSĂ (Quota Exceeded)"
            elif "403" in error_str:
                status_msg = f"⛔ {source_name}: ACCES INTERZIS (Verifică setările Google Cloud)"
            else:
                status_msg = f"⚠️ {source_name}: EROARE NECUNOSCUTĂ ({error_str[:30]}...)"
            
            logs.append(status_msg)
            last_error_msg = error_str
            # Continuăm la următoarea cheie din listă...

    # Dacă am ieșit din buclă, toate au eșuat
    return None, logs

# --- DATABASE (SQLite) ---
def init_db():
    conn = sqlite3.connect('chat_history.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            has_image BOOLEAN
        )
    ''')
    conn.commit()
    conn.close()

def save_message(session_id, role, content, has_image=False):
    conn = sqlite3.connect('chat_history.db')
    c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, has_image) VALUES (?, ?, ?, ?)',
              (session_id, role, content, has_image))
    conn.commit()
    conn.close()

def get_history(session_id):
    conn = sqlite3.connect('chat_history.db')
    c = conn.cursor()
    c.execute('SELECT role, content, has_image FROM messages WHERE session_id = ? ORDER BY id', (session_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def clear_session_history(session_id):
    conn = sqlite3.connect('chat_history.db')
    c = conn.cursor()
    c.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

init_db()

# --- URL SESSION ---
query_params = st.query_params
if "session_id" not in query_params:
    new_id = str(uuid.uuid4())
    st.query_params["session_id"] = new_id
    session_id = new_id
else:
    session_id = query_params["session_id"]

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2913/2913465.png", width=100)
    st.title("Atelier Virtual")
    
    # --- ZONA STATUS CHEI ---
    with st.expander("📡 Status Conexiune Server", expanded=True):
        if st.session_state.key_logs:
            for log in st.session_state.key_logs:
                if "❌" in log:
                    st.markdown(f"<div class='status-log key-expired'>{log}</div>", unsafe_allow_html=True)
                elif "✅" in log:
                    st.markdown(f"<div class='status-log key-success'>{log}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='status-log'>{log}</div>", unsafe_allow_html=True)
        else:
            st.caption("Așteaptă prima interacțiune...")

    # --- ZONA INPUT CHEIE MANUALĂ ---
    with st.expander("🔑 Introdu Cheie Proprie", expanded=st.session_state.api_error):
        st.caption("Dacă toate cheile serverului sunt expirate, introdu una personală.")
        user_key_input = st.text_input("Google API Key", value=st.session_state.user_api_key, type="password")
        if user_key_input != st.session_state.user_api_key:
            st.session_state.user_api_key = user_key_input
            st.session_state.api_error = False
            st.session_state.key_logs = [] 
            st.rerun()

    st.divider()
    if st.button("🔄 Resetează Conversația", type="primary"):
        clear_session_history(session_id)
        new_id = str(uuid.uuid4())
        st.query_params["session_id"] = new_id
        st.session_state.key_logs = []
        st.rerun()

# --- CHAT UI ---
st.title("🎨 Consultant Tradiții & Handmade")

# Afișare istoric
history_data = get_history(session_id)
for role, content, has_image in history_data:
    with st.chat_message(role):
        st.markdown(content)
        if has_image and role == "user":
            st.caption("*(Imagine analizată anterior)*")

# Inputuri
uploaded_file = st.file_uploader("Încarcă o poză (JPEG/PNG)", type=["jpg", "jpeg", "png"])
image_data = None
if uploaded_file:
    try:
        image = Image.open(uploaded_file)
        st.image(image, caption="Produs analizat", use_column_width=True)
        image_data = image
    except:
        pass

if prompt := st.chat_input("Scrie mesajul tău..."):
    # 1. Afișăm și salvăm ce a scris userul
    with st.chat_message("user"):
        st.markdown(prompt)
    save_message(session_id, "user", prompt, has_image=(uploaded_file is not None))

    # 2. Construim lista de input pentru Gemini
    # Începem cu Prompt-ul de sistem definit la început
    inputs = [SYSTEM_PROMPT]
    
    # Adăugăm istoricul recent pentru context
    for role, content, _ in history_data[-6:]:
        role_gemini = "user" if role == "user" else "model"
        inputs.append(f"{role_gemini}: {content}")
    
    # Adăugăm imaginea dacă există
    if image_data:
        inputs.append(image_data)
        inputs.append("Analizează imaginea atașată.")

    # Adăugăm întrebarea curentă
    inputs.append(f"user: {prompt}")

    # 3. Apelăm AI-ul cu sistemul de rotație
    with st.chat_message("assistant"):
        with st.spinner("Conectare la meșterul digital..."):
            
            # Resetăm logurile vechi
            st.session_state.key_logs = []
            
            # Apelăm funcția
            ai_text, logs = call_gemini_with_rotation(inputs)
            
            # Salvăm logurile
            st.session_state.key_logs = logs
            
            

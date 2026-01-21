import streamlit as st
import google.generativeai as genai
import sqlite3
import uuid
from PIL import Image
import io
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
</style>
""", unsafe_allow_html=True)

# --- INIȚIALIZARE SESSION STATE ---
if "user_api_key" not in st.session_state:
    st.session_state.user_api_key = ""
if "api_error" not in st.session_state:
    st.session_state.api_error = False

# --- GESTIONARE CHEI API (ROTAȚIE & FALLBACK) ---
def get_system_api_keys():
    """Extrage lista de chei din secrets, indiferent dacă e string sau listă."""
    try:
        keys = st.secrets["GOOGLE_API_KEYS"]
        if isinstance(keys, str):
            # Dacă userul le-a pus separate prin virgulă "key1,key2"
            return [k.strip() for k in keys.split(",") if k.strip()]
        elif isinstance(keys, list):
            return keys
        return []
    except:
        return []

def call_gemini_with_rotation(inputs):
    """
    Încearcă să genereze conținut folosind cheile disponibile în ordine:
    1. Cheia introdusă manual de user (dacă există).
    2. Cheile din server (loop).
    """
    # Colectăm toate cheile posibile
    available_keys = []
    
    # 1. Prioritate: Cheia utilizatorului
    if st.session_state.user_api_key:
        available_keys.append(st.session_state.user_api_key)
    
    # 2. Cheile din sistem
    system_keys = get_system_api_keys()
    available_keys.extend(system_keys)

    # Dacă nu avem nicio cheie, returnăm eroare specifică
    if not available_keys:
        return None, "NO_KEYS"

    last_error = ""
    
    # BUCLA DE ROTAȚIE
    for key in available_keys:
        try:
            # Configurăm Gemini cu cheia curentă
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Încercăm generarea
            response = model.generate_content(inputs)
            return response.text, None # Succes!
            
        except Exception as e:
            # Dacă eșuează, trecem la următoarea cheie
            last_error = str(e)
            continue 

    # Dacă am ieșit din buclă, înseamnă că toate cheile au eșuat
    return None, last_error

# Instrucțiuni de sistem
SYSTEM_PROMPT = """
Ești un expert în artă populară românească, tradiții, folclor și marketing pentru produse handmade.
Rolul tău este să ajuți un artist să creeze produse autentice (mărțișoare, cadouri de Crăciun, Paște).
1. Analizează pozele încărcate din punct de vedere estetic și al materialelor.
2. Sugerează îmbunătățiri cromatice sau materiale naturale (lemn, lână, lut) specifice sezonului.
3. Creează o poveste lungă, emoționantă, cu iz arhaic românesc pentru fiecare produs, pe care artistul să o pună pe etichetă sau pe social media.
Tonul trebuie să fie cald, încurajator și respectuos față de tradiție.
"""

# --- GESTIONARE BAZĂ DE DATE (SQLite) ---
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

# --- GESTIONARE SESIUNE URL ---
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
    
    # --- ZONA DE CHEIE API MANUALĂ ---
    # Apare doar dacă userul vrea să pună o cheie sau dacă avem eroare
    with st.expander("🔑 Setări Cheie API", expanded=st.session_state.api_error):
        st.caption("Dacă serverul este ocupat, poți folosi cheia ta personală.")
        user_key_input = st.text_input("Google API Key", value=st.session_state.user_api_key, type="password")
        if user_key_input != st.session_state.user_api_key:
            st.session_state.user_api_key = user_key_input
            st.session_state.api_error = False # Resetăm eroarea
            st.rerun()
            
    st.divider()
    if st.button("🔄 Resetează Conversația", type="primary"):
        clear_session_history(session_id)
        new_id = str(uuid.uuid4())
        st.query_params["session_id"] = new_id
        st.rerun()

# --- LOGICA DE CHAT ---
st.title("🎨 Consultant Tradiții & Handmade")

# Dacă a fost o eroare de API, afișăm avertismentul
if st.session_state.api_error:
    st.warning("⚠️ Toate cheile serverului sunt ocupate sau expirate. Te rog introdu o cheie Google API validă în meniul din stânga pentru a continua.")

# Afișare istoric
history_data = get_history(session_id)
for role, content, has_image in history_data:
    with st.chat_message(role):
        st.markdown(content)
        if has_image and role == "user":
            st.caption("*(Imagine analizată anterior)*")

# Input fișiere
uploaded_file = st.file_uploader("Încarcă o poză (JPEG/PNG) sau PDF", type=["jpg", "jpeg", "png", "pdf"])
image_data = None

if uploaded_file:
    try:
        if uploaded_file.type in ["image/jpeg", "image/png"]:
            image = Image.open(uploaded_file)
            st.image(image, caption="Produsul tău", use_column_width=True)
            image_data = image
    except Exception as e:
        st.error(f"Eroare fișier: {e}")

# Input text
if prompt := st.chat_input("Scrie aici..."):
    # Salvare și afișare mesaj user
    with st.chat_message("user"):
        st.markdown(prompt)
    save_message(session_id, "user", prompt, has_image=(uploaded_file is not None))

    # Pregătire input AI
    inputs = [SYSTEM_PROMPT]
    # Context (ultimele 6 mesaje pentru a economisi tokeni, dar a păstra firul)
    for role, content, _ in history_data[-6:]:
        role_gemini = "user" if role == "user" else "model"
        inputs.append(f"{role_gemini}: {content}")
    
    inputs.append(f"user: {prompt}")
    if image_data:
        inputs.append(image_data)

    # Generare Răspuns cu ROTAȚIE CHEI
    with st.chat_message("assistant"):
        with st.spinner("Caut inspirație..."):
            ai_text, error_msg = call_gemini_with_rotation(inputs)
            
            if ai_text:
                # SUCCES
                st.markdown(ai_text)
                save_message(session_id, "assistant", ai_text)
                st.session_state.api_error = False
            else:
                # EȘEC TOTAL
                if error_msg == "NO_KEYS":
                    st.error("Nu există nicio cheie API configurată.")
                else:
                    st.error(f"Nu am putut genera un răspuns. Detalii: {error_msg}")
                
                # Activăm flag-ul de eroare pentru a deschide meniul de setări
                st.session_state.api_error = True
                st.rerun()

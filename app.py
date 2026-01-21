import streamlit as st
import google.generativeai as genai
import sqlite3
import uuid
from PIL import Image
import io

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

# --- CONFIGURARE GEMINI API ---
# Se preia cheia din Streamlit Secrets
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEYS"])
except:
    st.error("Te rog configurează GOOGLE_API_KEYS în Streamlit Secrets!")
    st.stop()

# Modelul Gemini (Flash este rapid și multimodal)
model = genai.GenerativeModel('gemini-1.5-flash')

# Instrucțiuni de sistem (Persona AI-ului)
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

# Inițializăm baza de date la pornire
init_db()

# --- GESTIONARE SESIUNE (URL Query Params) ---
# Verificăm dacă există un ID în URL
query_params = st.query_params
if "session_id" not in query_params:
    # Generăm un ID nou și îl punem în URL
    new_id = str(uuid.uuid4())
    st.query_params["session_id"] = new_id
    session_id = new_id
else:
    # Folosim ID-ul existent
    session_id = query_params["session_id"]

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2913/2913465.png", width=100)
    st.title("Atelier Virtual")
    st.info(f"ID Sesiune: {session_id[:8]}...")
    st.markdown("Acest ID păstrează conversația chiar dacă închizi pagina.")
    
    if st.button("🔄 Resetează Conversația", type="primary"):
        clear_session_history(session_id)
        # Generăm un nou ID pentru a curăța complet contextul
        new_id = str(uuid.uuid4())
        st.query_params["session_id"] = new_id
        st.rerun()

# --- LOGICA DE CHAT ---
st.title("🎨 Consultant Tradiții & Handmade")
st.markdown("Încarcă o poză cu creația ta și hai să îi scriem povestea!")

# Încărcăm istoricul din baza de date în UI
history_data = get_history(session_id)

for role, content, has_image in history_data:
    with st.chat_message(role):
        st.markdown(content)
        if has_image and role == "user":
            st.caption("*(Imagine analizată anterior)*")

# Zona de input pentru fișiere
uploaded_file = st.file_uploader("Încarcă o poză (JPEG/PNG) sau PDF", type=["jpg", "jpeg", "png", "pdf"])
image_data = None

if uploaded_file:
    # Afișăm imaginea/fișierul
    try:
        if uploaded_file.type in ["image/jpeg", "image/png"]:
            image = Image.open(uploaded_file)
            st.image(image, caption="Produsul tău", use_column_width=True)
            image_data = image
        else:
            st.info("Fișier PDF încărcat. AI-ul îl va analiza.")
            # Pentru PDF e nevoie de procesare specială, dar Gemini acceptă bytes
            # Aici simplificăm tratând imaginile ca prioritate vizuală
    except Exception as e:
        st.error(f"Eroare la încărcare: {e}")

# Zona de input text
if prompt := st.chat_input("Despre ce produs vorbim azi?"):
    # 1. Afișăm mesajul utilizatorului
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # 2. Salvăm mesajul utilizatorului în DB
    save_message(session_id, "user", prompt, has_image=(uploaded_file is not None))

    # 3. Pregătim apelul către Gemini
    inputs = [SYSTEM_PROMPT] # Începem cu instrucțiunile
    
    # Adăugăm istoricul recent pentru context (ultimele 10 mesaje pentru a nu depăși tokenii rapid)
    for role, content, _ in history_data[-10:]:
        role_gemini = "user" if role == "user" else "model"
        inputs.append(f"{role_gemini}: {content}")
    
    # Adăugăm inputul curent
    inputs.append(f"user: {prompt}")

    # Dacă avem imagine, o adăugăm la request
    if image_data:
        inputs.append(image_data)
        inputs.append("Analizează această imagine în contextul cerinței.")

    # 4. Generăm răspunsul
    with st.chat_message("assistant"):
        with st.spinner("Meșterul AI gândește..."):
            try:
                response = model.generate_content(inputs)
                ai_text = response.text
                st.markdown(ai_text)
                
                # 5. Salvăm răspunsul AI în DB
                save_message(session_id, "assistant", ai_text)
                
            except Exception as e:
                st.error(f"A apărut o eroare de conexiune cu Google: {e}")

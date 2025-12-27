import streamlit as st
import sqlite3
import hashlib
import pdfplumber
import re
import os

# --- 1. SETUP THE PAGE ---
st.set_page_config(page_title="Loco Quiz Portal", layout="wide")

# --- 2. DATABASE (To save logins & progress) ---
def init_db():
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS progress (username TEXT, topic TEXT, q_index INTEGER, score INTEGER, PRIMARY KEY (username, topic))')
    conn.commit()
    conn.close()

def signup(user, pwd):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (user,))
    if c.fetchone(): return False # User already exists
    c.execute('INSERT INTO users VALUES (?,?)', (user, hashlib.sha256(pwd.encode()).hexdigest()))
    conn.commit()
    conn.close()
    return True

def login(user, pwd):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (user, hashlib.sha256(pwd.encode()).hexdigest()))
    return c.fetchone() is not None

def save_progress(user, topic, idx, score):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO progress VALUES (?, ?, ?, ?)', (user, topic, idx, score))
    conn.commit()
    conn.close()

def load_progress(user, topic):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('SELECT q_index, score FROM progress WHERE username = ? AND topic = ?', (user, topic))
    data = c.fetchone()
    conn.close()
    return data if data else (0, 0)

# --- 3. READ THE PDF ---
@st.cache_data
def parse_pdf(uploaded_file):
    # This function reads your specific PDF format
    questions = {}
    current_topic = "General Questions"
    questions[current_topic] = []
    
    with pdfplumber.open(uploaded_file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    
    # Logic to split text into questions based on your PDF style
    lines = text.split('\n')
    current_q = None
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Detect Topic (e.g., "1. General Rules...")
        if re.match(r'^\d+\.\s+[A-Z]', line) and "Answer" not in line and len(line) < 80:
            current_topic = line
            if current_topic not in questions: questions[current_topic] = []
            continue
            
        # Detect New Question Start (e.g., "1.", "105.")
        if re.match(r'^"?\d+\."?', line):
            if current_q: questions[current_topic].append(current_q)
            current_q = {"q": line, "options": [], "ans": None}
        
        # Detect Answer Key (e.g., "(B)")
        elif current_q and re.search(r'\(\s*[A-D]\s*\)', line):
            ans = re.search(r'\(\s*([A-D])\s*\)', line).group(1)
            current_q['ans'] = ans
            # Clean the line
            clean_line = re.sub(r'\(\s*[A-D]\s*\)', '', line).strip()
            if clean_line: current_q['options'].append(clean_line)
            
        # Detect Options (A), B), etc.)
        elif current_q and (line.startswith("A)") or line.startswith("B)") or line.startswith("C)") or line.startswith("D)")):
            current_q['options'].append(line)
        
        # Continuation of text
        elif current_q:
            if not current_q['options']:
                current_q['q'] += " " + line
            else:
                current_q['options'][-1] += " " + line
                
    if current_q: questions[current_topic].append(current_q)
    return {k: v for k,v in questions.items() if v}

# --- 4. THE WEBSITE LAYOUT ---
init_db()

if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.user:
    st.title("🚆 Quiz Login")
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Log In"):
            if login(u, p):
                st.session_state.user = u
                st.rerun()
            else: st.error("Wrong credentials")
            
    with tab2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        if st.button("Sign Up"):
            if signup(nu, np): st.success("Created! Go to Login.")
            else: st.error("Username taken.")

else:
    # LOGGED IN VIEW
    st.sidebar.write(f"Logged in as: **{st.session_state.user}**")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()
    
    st.title("Quiz Dashboard")
    
    # Load PDF
    pdf_name = "Question PDF.PDF"
    if not os.path.exists(pdf_name):
        st.error(f"Please upload '{pdf_name}' to GitHub!")
    else:
        data = parse_pdf(pdf_name)
        topic = st.sidebar.selectbox("Select Topic", list(data.keys()))
        
        # Get Progress
        q_list = data[topic]
        current_idx, score = load_progress(st.session_state.user, topic)
        
        # Progress Bar
        progress = int((current_idx / len(q_list)) * 100) if q_list else 0
        st.sidebar.write(f"Topic Progress: {progress}%")
        st.sidebar.progress(progress)
        
        if current_idx < len(q_list):
            q_data = q_list[current_idx]
            st.subheader(f"Question {current_idx + 1} / {len(q_list)}")
            st.write(q_data['q'])
            
            st.write("**Options:**")
            for opt in q_data['options']:
                st.text(opt)
                
            choice = st.radio("Choose Answer:", ["A", "B", "C", "D"], horizontal=True, key=f"q{current_idx}")
            
            if st.button("Submit"):
                correct = q_data.get('ans', '').strip()
                if choice == correct:
                    st.success("Correct!")
                    save_progress(st.session_state.user, topic, current_idx + 1, score + 1)
                else:
                    st.error(f"Wrong! Correct was {correct}")
                    save_progress(st.session_state.user, topic, current_idx + 1, score)
                st.rerun()
        else:
            st.success("Topic Completed!")
            st.write(f"Final Score: {score}/{len(q_list)}")
            if st.button("Reset Topic"):
                save_progress(st.session_state.user, topic, 0, 0)
                st.rerun()

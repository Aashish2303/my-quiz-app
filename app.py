import streamlit as st
import sqlite3
import hashlib
import pdfplumber
import re
import os

# --- PAGE SETUP ---
st.set_page_config(page_title="Loco Quiz Portal", layout="wide")

# --- DATABASE FUNCTIONS ---
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
    if c.fetchone(): return False
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

# --- SMART PDF PARSER ---
@st.cache_data
def parse_pdf_smart():
    # 1. FIND THE FILE (Case Insensitive)
    files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not files:
        return None, "No PDF file found in GitHub repository!"
    
    pdf_path = files[0] # Use the first PDF found
    questions = {}
    current_topic = "General Questions"
    questions[current_topic] = []
    
    # 2. EXTRACT TEXT
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    except Exception as e:
        return None, f"Error reading PDF: {e}"

    # 3. FIND QUESTIONS
    lines = text.split('\n')
    current_q = None
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Topic Detection (Lines starting with number and letters, usually headers)
        # We make this stricter to avoid confusing it with questions
        if re.match(r'^\d+\.\s+[A-Z][a-z]+', line) and "Answer" not in line and len(line) < 100:
            # It's likely a topic header
            current_topic = line
            if current_topic not in questions: questions[current_topic] = []
            continue

        # Question Detection (Starts with "1." or "105.")
        # We strip quotes just in case
        clean_line = line.replace('"', '')
        if re.match(r'^\d+\.', clean_line):
            if current_q: questions[current_topic].append(current_q)
            current_q = {"q": clean_line, "options": [], "ans": None}
            continue
        
        # Answer Key Detection (Matches "(B)" or "( B )")
        ans_match = re.search(r'\(\s*([A-D])\s*\)', line)
        if current_q and ans_match:
            current_q['ans'] = ans_match.group(1)
            # Remove the answer part from line to see if there is option text left
            line = re.sub(r'\(\s*[A-D]\s*\)', '', line).strip()
            
        # Option Detection (A) ... B) ...)
        if current_q:
            if re.match(r'^[A-D]\)', line) or re.match(r'^\(?[A-D]\)', line):
                current_q['options'].append(line)
            elif any(m in line for m in ["A)", "B)", "C)", "D)"]):
                 current_q['options'].append(line)
            elif line:
                # Just text belonging to previous line
                if not current_q['options']:
                    current_q['q'] += " " + line
                else:
                    current_q['options'][-1] += " " + line

    # Save last question
    if current_q: questions[current_topic].append(current_q)
    
    # Remove empty topics
    final_data = {k: v for k,v in questions.items() if v}
    
    if not final_data:
        return None, f"Found file '{pdf_path}' but could not find any questions inside it! (Check PDF format)"
        
    return final_data, f"Success! Loaded {sum(len(v) for v in final_data.values())} questions from {pdf_path}"

# --- MAIN APP ---
init_db()

if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.user:
    st.title("🚆 Quiz Portal Login")
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Log In"):
            if login(u, p):
                st.session_state.user = u
                st.rerun()
            else: st.error("Invalid Username or Password")
            
    with tab2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        if st.button("Sign Up"):
            if signup(nu, np): st.success("Account created! Go to Login.")
            else: st.error("Username already taken.")

else:
    # --- LOGGED IN DASHBOARD ---
    st.sidebar.markdown(f"👤 **{st.session_state.user}**")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()
    
    st.title("📝 Quiz Dashboard")
    
    # LOAD DATA
    data, message = parse_pdf_smart()
    
    if not data:
        st.error(message) # Show exact error if something is wrong
    else:
        # st.success(message) # Uncomment this to see debug success message
        
        # TOPIC SELECTOR
        topic_list = list(data.keys())
        topic = st.sidebar.selectbox("Select Topic", topic_list)
        
        # QUIZ LOGIC
        q_list = data[topic]
        current_idx, score = load_progress(st.session_state.user, topic)
        
        # PROGRESS BAR
        total = len(q_list)
        progress = int((current_idx / total) * 100) if total > 0 else 0
        st.sidebar.write(f"**Progress:** {progress}%")
        st.sidebar.progress(progress)
        
        if current_idx < total:
            q = q_list[current_idx]
            
            st.markdown(f"### Question {current_idx + 1} / {total}")
            st.info(q['q'])
            
            st.write("**Options:**")
            # Display options clearly
            for opt in q['options']:
                st.text(opt)
                
            # Selection
            sel = st.radio("Your Answer:", ["A", "B", "C", "D"], horizontal=True, key=f"ans_{topic}_{current_idx}")
            
            if st.button("Submit Answer"):
                correct = q.get('ans', '').strip()
                if sel == correct:
                    st.success("✅ Correct!")
                    save_progress(st.session_state.user, topic, current_idx + 1, score + 1)
                else:
                    st.error(f"❌ Wrong! The answer was {correct}")
                    save_progress(st.session_state.user, topic, current_idx + 1, score)
                st.rerun()
                
        else:
            st.balloons()
            st.success(f"🎉 Topic Completed! Score: {score}/{total}")
            if st.button("Restart Topic"):
                save_progress(st.session_state.user, topic, 0, 0)
                st.rerun()

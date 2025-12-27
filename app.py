import streamlit as st
import sqlite3
import hashlib
import pdfplumber
import re
import os

st.set_page_config(page_title="Loco Inspector Quiz", layout="wide")

# --- 1. DATABASE SETUP (Login System) ---
def init_db():
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS progress (username TEXT, topic TEXT, q_index INTEGER, score INTEGER, PRIMARY KEY (username, topic))')
    conn.commit()
    conn.close()

def login_user(user, pwd):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (user, hashlib.sha256(pwd.encode()).hexdigest()))
    return c.fetchone() is not None

def register_user(user, pwd):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users VALUES (?,?)', (user, hashlib.sha256(pwd.encode()).hexdigest()))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def save_progress(user, topic, idx, score):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO progress VALUES (?, ?, ?, ?)', (user, topic, idx, score))
    conn.commit()
    conn.close()

def get_progress(user, topic):
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('SELECT q_index, score FROM progress WHERE username = ? AND topic = ?', (user, topic))
    data = c.fetchone()
    conn.close()
    return data if data else (0, 0)

# --- 2. FULL PDF PARSER ---
@st.cache_data
def load_data_full():
    # Find PDF
    files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not files: return None, "No PDF found."
    
    pdf_path = files[0]
    questions = {}
    current_topic = "General Questions"
    questions[current_topic] = []
    
    # Extract Text from ALL Pages
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t: text += t + "\n"

    lines = text.split('\n')
    current_q = None
    
    # Regex to handle your specific PDF format (quotes and commas)
    # This looks for "1." or "105." at the start of a line
    q_start = re.compile(r'^\s*"?\d+\."?') 
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Clean the line: remove csv-style quotes and leading commas
        clean_line = line.replace('"', '').replace("'", "")
        if clean_line.startswith(','): clean_line = clean_line[1:].strip()
        
        # 1. New Question Detection
        if q_start.match(clean_line):
            if current_q: questions[current_topic].append(current_q)
            current_q = {"q": clean_line, "options": [], "ans": None}
            
            # Check for Answer Key on same line: "1. Question... (B)"
            ans_match = re.search(r'\(\s*([A-D])\s*\)', clean_line)
            if ans_match:
                current_q['ans'] = ans_match.group(1)
        
        # 2. Answer Key Detection: "( B )" or "(B)"
        elif current_q and re.search(r'\(\s*([A-D])\s*\)', clean_line):
             ans = re.search(r'\(\s*([A-D])\s*\)', clean_line).group(1)
             current_q['ans'] = ans
             
        # 3. Option Detection: Starts with "A)", "B)" or "A.", "B."
        elif current_q and (re.match(r'^[A-D]\)', clean_line) or re.match(r'^[A-D]\.', clean_line)):
             current_q['options'].append(clean_line)
        
        # 4. Continuation Text
        elif current_q:
            # Avoid adding short garbage lines
            if len(clean_line) > 2:
                if not current_q['options']:
                    current_q['q'] += " " + clean_line
                else:
                    current_q['options'][-1] += " " + clean_line

    if current_q: questions[current_topic].append(current_q)
    
    return {k:v for k,v in questions.items() if len(v)>0}, "Loaded"

# --- 3. MAIN APP ---
init_db()

# Check Login
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.user:
    st.markdown("## 🚂 Loco Inspector Quiz")
    t1, t2 = st.tabs(["Login", "Register"])
    
    with t1:
        u = st.text_input("Username", key="l_u")
        p = st.text_input("Password", type="password", key="l_p")
        if st.button("Login"):
            if login_user(u, p):
                st.session_state.user = u
                st.rerun()
            else: st.error("Incorrect username or password")
            
    with t2:
        nu = st.text_input("New Username", key="r_u")
        np = st.text_input("New Password", type="password", key="r_p")
        if st.button("Create Account"):
            if register_user(nu, np): st.success("Created! You can Login now.")
            else: st.error("Username already taken.")

else:
    # Dashboard
    st.sidebar.title(f"User: {st.session_state.user}")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()
        
    data, msg = load_data_full()
    
    if not data:
        st.error("⚠️ Error: No questions found.")
        st.write(msg)
    else:
        # Topic Selection
        topics = list(data.keys())
        topic = st.sidebar.selectbox("Select Topic", topics)
        
        # Load User Progress
        q_list = data[topic]
        curr_idx, score = get_progress(st.session_state.user, topic)
        
        # Progress Bar
        total_q = len(q_list)
        if total_q > 0:
            pct = int((curr_idx / total_q) * 100)
            st.sidebar.write(f"**Progress: {pct}%**")
            st.sidebar.progress(pct)
        
        # Display Question
        if curr_idx < total_q:
            q_data = q_list[curr_idx]
            
            st.subheader(f"Question {curr_idx + 1} / {total_q}")
            st.info(q_data['q'])
            
            st.write("**Options:**")
            for opt in q_data['options']:
                st.text(opt)
            
            # Helper if options are empty
            if not q_data['options']:
                st.warning("Options text could not be read cleanly. Select A/B/C/D based on your knowledge.")

            # Answer Input
            user_choice = st.radio("Select Answer:", ["A", "B", "C", "D"], horizontal=True, key=f"q_{topic}_{curr_idx}")
            
            if st.button("Submit Answer"):
                correct = q_data.get('ans')
                
                # If PDF didn't have answer key extracted
                if not correct:
                    st.warning("No answer key found in PDF for this question.")
                    save_progress(st.session_state.user, topic, curr_idx + 1, score)
                    st.rerun()
                
                elif user_choice == correct:
                    st.success("✅ Correct!")
                    save_progress(st.session_state.user, topic, curr_idx + 1, score + 1)
                    st.rerun()
                else:
                    st.error(f"❌ Wrong! Correct answer: {correct}")
                    save_progress(st.session_state.user, topic, curr_idx + 1, score)
                    st.rerun()
        else:
            st.balloons()
            st.success(f"🎉 Topic '{topic}' Completed! Score: {score} / {total_q}")
            if st.button("Reset Topic"):
                save_progress(st.session_state.user, topic, 0, 0)
                st.rerun()

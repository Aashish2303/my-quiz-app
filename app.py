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

# --- 2. MESSY PDF PARSER ---
@st.cache_data
def load_data_messy():
    # Find PDF
    files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not files: return None, "No PDF found."
    
    pdf_path = files[0]
    questions = {}
    current_topic = "General Questions"
    questions[current_topic] = []
    
    # Extract Text
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t: text += t + "\n"

    lines = text.split('\n')
    current_q = None
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # --- CLEAN THE LINE (The Fix) ---
        # Remove quotes and leading commas usually found in this specific PDF
        clean_line = line.replace('"', '').replace("'", "")
        if clean_line.startswith(','): clean_line = clean_line[1:].strip()
        
        # 1. Detect Question Start (e.g. 1. or 105.)
        # We look for a number followed by a dot at the VERY START
        if re.match(r'^\d+\.', clean_line):
            # Save previous question
            if current_q: questions[current_topic].append(current_q)
            
            current_q = {
                "q": clean_line, 
                "options": [], 
                "ans": None
            }
            # Check if answer key is on the same line like "1. Question... (B)"
            ans_match = re.search(r'\(\s*([A-D])\s*\)', clean_line)
            if ans_match:
                current_q['ans'] = ans_match.group(1)
        
        # 2. Detect Answer Key (B) or ( B ) on its own line
        elif current_q and re.search(r'\(\s*([A-D])\s*\)', clean_line):
             ans = re.search(r'\(\s*([A-D])\s*\)', clean_line).group(1)
             current_q['ans'] = ans
             
        # 3. Detect Options (Starts with A) or A.)
        elif current_q and (re.match(r'^[A-D]\)', clean_line) or re.match(r'^[A-D]\.', clean_line)):
             current_q['options'].append(clean_line)
             
        # 4. Continuation Text
        elif current_q:
            # If line is just "A)" or "B)" skip it, otherwise append text
            if len(clean_line) > 3:
                if not current_q['options']:
                    current_q['q'] += " " + clean_line
                else:
                    current_q['options'][-1] += " " + clean_line

    if current_q: questions[current_topic].append(current_q)
    
    # Remove empty stuff
    return {k:v for k,v in questions.items() if len(v)>0}, "Loaded"

# --- 3. THE APP INTERFACE ---
init_db()

# Login Screen
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.user:
    st.markdown("## 🚂 Loco Quiz Portal")
    t1, t2 = st.tabs(["Login", "Register"])
    
    with t1:
        u = st.text_input("Username", key="l_u")
        p = st.text_input("Password", type="password", key="l_p")
        if st.button("Login"):
            if login_user(u, p):
                st.session_state.user = u
                st.rerun()
            else: st.error("Wrong username or password")
            
    with t2:
        nu = st.text_input("Choose Username", key="r_u")
        np = st.text_input("Choose Password", type="password", key="r_p")
        if st.button("Create Account"):
            if register_user(nu, np): st.success("Account Created! You can Login now.")
            else: st.error("Username taken.")

else:
    # Quiz Screen
    st.sidebar.write(f"Logged in as: **{st.session_state.user}**")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()
        
    data, msg = load_data_messy()
    
    if not data:
        st.error("⚠️ Could not read questions from PDF. (Format issue)")
        st.write("Debug info: " + msg)
    else:
        # Topic Select
        topics = list(data.keys())
        topic = st.sidebar.selectbox("Select Section", topics)
        
        # Get Data
        questions = data[topic]
        curr_idx, score = get_progress(st.session_state.user, topic)
        
        # Progress Bar
        bar = st.sidebar.progress(0)
        if len(questions) > 0:
            pct = int((curr_idx / len(questions)) * 100)
            bar.progress(pct)
            st.sidebar.write(f"Progress: {pct}%")
        
        # Show Question
        if curr_idx < len(questions):
            q_data = questions[curr_idx]
            
            st.markdown(f"#### Question {curr_idx + 1}")
            st.info(q_data['q'])
            
            # Options
            opts = q_data['options']
            if not opts: st.warning("No options found for this question (check PDF format).")
            
            # Radio button needs unique key
            user_choice = st.radio("Choose:", ["A", "B", "C", "D"], horizontal=True, key=f"q_{topic}_{curr_idx}")
            
            if st.button("Submit Answer"):
                correct_ans = q_data.get('ans')
                
                # Handle missing answer key in PDF
                if not correct_ans:
                    st.warning("⚠️ This question has no answer key in the PDF!")
                    # Allow skip
                    save_progress(st.session_state.user, topic, curr_idx + 1, score)
                    st.rerun()
                
                elif user_choice == correct_ans:
                    st.success("✅ Correct!")
                    save_progress(st.session_state.user, topic, curr_idx + 1, score + 1)
                    st.rerun()
                else:
                    st.error(f"❌ Wrong! The correct answer was ({correct_ans})")
                    save_progress(st.session_state.user, topic, curr_idx + 1, score)
                    st.rerun() # Wait for user to click next or auto refresh
        else:
            st.balloons()
            st.success(f"🎉 Section Complete! Score: {score}/{len(questions)}")
            if st.button("Reset this Section"):
                save_progress(st.session_state.user, topic, 0, 0)
                st.rerun()

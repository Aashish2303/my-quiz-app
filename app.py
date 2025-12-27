import streamlit as st
import sqlite3
import hashlib
import pdfplumber
import re
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Loco Quiz Portal", layout="centered")

# --- 1. DATABASE (Login & Progress) ---
def init_db():
    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT)')
    # Progress: username, topic, current_question_index, current_score
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

# --- 2. ADVANCED PDF PARSER ---
@st.cache_data
def parse_pdf_robust():
    # Find the PDF
    files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not files: return None, "No PDF found."
    pdf_path = files[0]

    questions_by_topic = {}
    current_topic = "General Questions" # Default if no header found
    questions_by_topic[current_topic] = []
    
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t: text += t + "\n"

    lines = text.split('\n')
    current_q = None
    
    # REGEX PATTERNS
    # Topic Header: "1. General Rules" (No quotes typically)
    # We look for lines that START with a number, but DO NOT have quotes around the number
    topic_pattern = re.compile(r'^\d+\.\s+[A-Za-z]') 
    
    # Question Start: "1." or "105." (Often has quotes in your PDF)
    # We look for a number followed by a dot
    question_pattern = re.compile(r'^"?\d+\."?') 

    for line in lines:
        line = line.strip()
        if not line: continue
        
        # --- CHECK FOR TOPIC HEADER ---
        # If line is "1. Something..." and NOT a question (no answer keys nearby)
        if topic_pattern.match(line) and "Answer" not in line and len(line) < 100:
            # It's a Topic!
            current_topic = line
            if current_topic not in questions_by_topic:
                questions_by_topic[current_topic] = []
            current_q = None
            continue

        # --- CLEAN MESSY TEXT ---
        # Remove CSV-style quotes: '"1.",' -> '1.'
        clean_line = line.replace('"', '').replace("'", "")
        if clean_line.startswith(','): clean_line = clean_line[1:].strip()
        
        # --- CHECK FOR QUESTION ---
        if question_pattern.match(clean_line):
            # Save previous question
            if current_q: questions_by_topic[current_topic].append(current_q)
            
            current_q = {"q": clean_line, "options": [], "ans": None}
            
            # Check for inline answer: "1. Question... (B)"
            ans_match = re.search(r'\(\s*([A-D])\s*\)', clean_line)
            if ans_match:
                current_q['ans'] = ans_match.group(1)

        # --- CHECK FOR ANSWERS & OPTIONS ---
        elif current_q:
            # Detect Answer Key: "( B )"
            ans_match = re.search(r'\(\s*([A-D])\s*\)', clean_line)
            if ans_match:
                current_q['ans'] = ans_match.group(1)
            
            # Detect Options: "A)...", "B)..."
            if re.match(r'^[A-D]\)', clean_line) or re.match(r'^[A-D]\.', clean_line):
                 current_q['options'].append(clean_line)
            elif any(x in clean_line for x in ["A)", "B)", "C)", "D)"]):
                 # Handle multi-option lines
                 current_q['options'].append(clean_line)
            else:
                 # Text continuation
                 if len(clean_line) > 3: # Ignore small garbage
                    if not current_q['options']:
                        current_q['q'] += " " + clean_line
                    else:
                        current_q['options'][-1] += " " + clean_line

    if current_q: questions_by_topic[current_topic].append(current_q)
    
    # Remove empty topics
    return {k:v for k,v in questions_by_topic.items() if len(v) > 0}, "Loaded"

# --- 3. MAIN APPLICATION ---
init_db()

# Session State Management
if 'user' not in st.session_state: st.session_state.user = None
if 'active_topic' not in st.session_state: st.session_state.active_topic = None
if 'quiz_state' not in st.session_state: st.session_state.quiz_state = "QUESTION" # States: QUESTION, FEEDBACK

# --- VIEW 1: LOGIN SCREEN ---
if not st.session_state.user:
    st.markdown("<h1 style='text-align: center;'>🚂 Loco Inspector Quiz</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Log In", use_container_width=True):
            if login_user(u, p):
                st.session_state.user = u
                st.rerun()
            else: st.error("Invalid Username or Password")
            
    with tab2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        if st.button("Create Account", use_container_width=True):
            if register_user(nu, np): st.success("Account Created! Please Log In.")
            else: st.error("Username already taken.")

# --- VIEW 2: LOGGED IN ---
else:
    # Sidebar
    st.sidebar.write(f"👤 **{st.session_state.user}**")
    if st.sidebar.button("🏠 Home / Topics"):
        st.session_state.active_topic = None
        st.session_state.quiz_state = "QUESTION"
        st.rerun()
    if st.sidebar.button("🚪 Logout"):
        st.session_state.user = None
        st.session_state.active_topic = None
        st.rerun()

    # Load Data
    data, msg = parse_pdf_robust()

    if not data:
        st.error("No questions found. Please check PDF.")
    
    # --- VIEW 2A: TOPIC DASHBOARD (List of Topics) ---
    elif st.session_state.active_topic is None:
        st.title("📚 Select a Topic")
        
        topics = list(data.keys())
        for topic in topics:
            # Get progress for this topic
            q_count = len(data[topic])
            c_idx, c_score = get_progress(st.session_state.user, topic)
            pct = int((c_idx / q_count) * 100) if q_count > 0 else 0
            
            # Create a card for the topic
            with st.container():
                st.markdown(f"### {topic}")
                st.progress(pct)
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.write(f"**{pct}% Done**")
                with col2:
                    if st.button(f"Start / Continue", key=topic):
                        st.session_state.active_topic = topic
                        st.rerun()
                st.markdown("---")

    # --- VIEW 2B: QUIZ INTERFACE ---
    else:
        topic = st.session_state.active_topic
        questions = data[topic]
        
        # Get current progress
        current_idx, current_score = get_progress(st.session_state.user, topic)
        
        # Header
        st.markdown(f"### Topic: {topic}")
        st.progress(int((current_idx / len(questions)) * 100))
        
        # Check completion
        if current_idx >= len(questions):
            st.success("🎉 You have completed this topic!")
            st.write(f"**Final Score: {current_score} / {len(questions)}**")
            if st.button("🔄 Reset & Practice Again"):
                save_progress(st.session_state.user, topic, 0, 0)
                st.rerun()
            if st.button("⬅️ Back to Topics"):
                st.session_state.active_topic = None
                st.rerun()
        else:
            # DISPLAY QUESTION
            q_data = questions[current_idx]
            
            st.info(f"**Q{current_idx + 1}:** {q_data['q']}")
            
            # Show Options
            st.write("Options:")
            for opt in q_data['options']:
                st.text(opt)
            if not q_data['options']: st.caption("(No options text detected)")

            # --- INTERACTION AREA ---
            # We use a placeholder to manage the feedback loop
            
            # If we are in "FEEDBACK" state, show the result
            if st.session_state.get(f"feedback_{topic}_{current_idx}"):
                res = st.session_state[f"feedback_{topic}_{current_idx}"]
                if res['correct']:
                    st.success("✅ Correct Answer!")
                else:
                    st.error(f"❌ Wrong! The correct answer was: {res['ans']}")
                
                if st.button("Next Question ➡️"):
                    # Save progress and move on
                    new_score = current_score + (1 if res['correct'] else 0)
                    save_progress(st.session_state.user, topic, current_idx + 1, new_score)
                    # Clear feedback state
                    del st.session_state[f"feedback_{topic}_{current_idx}"]
                    st.rerun()

            # If we are in "QUESTION" state, show inputs
            else:
                user_choice = st.radio("Select Answer:", ["A", "B", "C", "D"], horizontal=True, key=f"radio_{topic}_{current_idx}")
                
                if st.button("Submit Answer"):
                    correct_ans = q_data.get('ans')
                    
                    if not correct_ans:
                        st.warning("No answer key found in PDF. Skipping...")
                        save_progress(st.session_state.user, topic, current_idx + 1, current_score)
                        st.rerun()
                    else:
                        # Store result in session state NOT database yet
                        is_correct = (user_choice == correct_ans)
                        st.session_state[f"feedback_{topic}_{current_idx}"] = {
                            "correct": is_correct,
                            "ans": correct_ans
                        }
                        st.rerun()

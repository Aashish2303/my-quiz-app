import streamlit as st
import sqlite3
import hashlib
import pdfplumber
import re
import os

st.set_page_config(page_title="Loco Inspector Quiz", layout="wide")

# --- DATABASE SETUP ---
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

# --- PDF PARSER (DEBUG MODE) ---
@st.cache_data
def load_data_debug():
    # 1. Find PDF
    files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not files:
        return None, "❌ No PDF found! Please upload 'Question PDF.PDF' to GitHub."
    
    pdf_path = files[0]
    debug_text = ""
    
    # 2. Extract Text
    full_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
                    if i == 0: debug_text = page_text[:1000] # Save 1st page for debug
    except Exception as e:
        return None, f"❌ Error reading PDF: {e}"

    if len(full_text) < 100:
        return None, "❌ The PDF seems empty or unreadable (scanned image?)."

    # 3. Simple Parsing
    questions = {}
    current_topic = "All Questions" # Default topic
    questions[current_topic] = []
    
    lines = full_text.split('\n')
    current_q = None
    
    # REGEX HELPERS
    # Matches "1." or "105." or "1 ." at start of line
    q_pattern = re.compile(r'^\s*(\d+)\s*\.') 
    # Matches "1. General Rules" (Topic detection)
    topic_pattern = re.compile(r'^\s*\d+\.\s+[A-Z].*(Rules|Manual|Section|CHAPTER)')
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Check for Topic (Optional - can be disabled if causing issues)
        if topic_pattern.match(line) and len(line) < 100:
            current_topic = line
            if current_topic not in questions: questions[current_topic] = []
            current_q = None # Reset
            continue

        # Check for Question Start
        match = q_pattern.match(line)
        if match:
            # If we were building a question, save it
            if current_q: questions[current_topic].append(current_q)
            
            # Start new question
            current_q = {
                "q": line, 
                "options": [], 
                "ans": None
            }
        
        # If we are inside a question
        elif current_q:
            # Check for Answer Key: (A) or (B)
            ans_match = re.search(r'\(\s*([A-D])\s*\)', line)
            if ans_match:
                current_q["ans"] = ans_match.group(1)
                # Remove answer key from text
                line = re.sub(r'\(\s*[A-D]\s*\)', '', line).strip()
            
            # Check for Options: A) ... B) ...
            if re.match(r'^[A-D]\)', line) or re.match(r'^\(?[A-D]\)', line):
                 current_q["options"].append(line)
            elif any(x in line for x in [" A)", " B)", " C)", " D)"]):
                 # Attempt to split lines that have multiple options like "A) ... B) ..."
                 current_q["options"].append(line)
            else:
                 # Just text continuation
                 if not current_q["options"]:
                     current_q["q"] += " " + line
                 else:
                     current_q["options"][-1] += " " + line

    # Save last question
    if current_q: questions[current_topic].append(current_q)
    
    # Filter empty topics
    final_data = {k:v for k,v in questions.items() if v}
    
    if not final_data:
        return None, f"❌ Parsed {len(lines)} lines but found 0 questions. \n\n**Debug View (First 500 chars):**\n{debug_text}..."
        
    return final_data, f"✅ Success! Found {sum(len(v) for v in final_data.values())} questions."

# --- MAIN APP ---
init_db()

if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.user:
    st.title("🚂 Loco Inspector Quiz")
    tab1, tab2 = st.tabs(["Login", "Register"])
    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if login_user(u, p):
                st.session_state.user = u
                st.rerun()
            else: st.error("Invalid credentials")
    with tab2:
        nu = st.text_input("New User")
        np = st.text_input("New Pass", type="password")
        if st.button("Register"):
            if register_user(nu, np): st.success("Created! Login now.")
            else: st.error("User exists")
else:
    # LOGGED IN
    st.sidebar.markdown(f"User: **{st.session_state.user}**")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()
        
    data, msg = load_data_debug()
    
    # --- DEBUG SECTION ---
    with st.expander("Show System Status"):
        st.write(msg)
    
    if data:
        topic = st.sidebar.selectbox("Select Topic", list(data.keys()))
        q_list = data[topic]
        idx, score = get_progress(st.session_state.user, topic)
        
        # Progress Bar
        pct = int((idx / len(q_list)) * 100)
        st.sidebar.progress(pct)
        st.sidebar.write(f"{pct}% Complete")
        
        if idx < len(q_list):
            q = q_list[idx]
            st.markdown(f"### Question {idx+1}")
            st.info(q['q'])
            st.write("Options:")
            for o in q['options']: st.text(o)
            
            sel = st.radio("Answer:", ["A","B","C","D"], horizontal=True, key=f"{topic}_{idx}")
            if st.button("Submit"):
                corr = q.get('ans', '').strip()
                if sel == corr:
                    st.success("Correct! ✅")
                    save_progress(st.session_state.user, topic, idx+1, score+1)
                else:
                    st.error(f"Wrong! Answer: {corr}")
                    save_progress(st.session_state.user, topic, idx+1, score)
                st.rerun()
        else:
            st.success(f"Topic Finished! Score: {score}/{len(q_list)}")
            if st.button("Reset"):
                save_progress(st.session_state.user, topic, 0, 0)
                st.rerun()
    else:
        st.error("Could not load questions. Check the Debug section above.")

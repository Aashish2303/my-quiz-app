import streamlit as st
import os

st.title("📂 System File Scanner")

# 1. Check if we can import the PDF tool
try:
    import pdfplumber
    st.success("✅ 'pdfplumber' library is installed correctly.")
except ImportError:
    st.error("❌ CRITICAL ERROR: 'pdfplumber' is NOT installed. Check requirements.txt!")
    st.stop()

# 2. List all files in the current folder
files = os.listdir('.')
st.write("### Files found in the main folder:")
st.write(files)

# 3. Look specifically for PDFs
pdf_files = [f for f in files if f.lower().endswith('.pdf')]

if not pdf_files:
    st.error("❌ No PDF files found! The server cannot see your file.")
    st.info("Tip: Did you upload it to a subfolder? It must be in the main folder.")
else:
    st.success(f"✅ Found PDF: {pdf_files[0]}")
    
    # 4. Try to read the first page
    st.write("### Attempting to read PDF content...")
    try:
        with pdfplumber.open(pdf_files[0]) as pdf:
            if len(pdf.pages) > 0:
                first_page_text = pdf.pages[0].extract_text()
                st.write("**Success! First 500 characters of text:**")
                st.text(first_page_text[:500])
            else:
                st.warning("⚠️ The PDF opens, but has 0 pages?")
    except Exception as e:
        st.error(f"❌ Error opening file: {e}")

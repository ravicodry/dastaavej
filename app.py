import streamlit as st
import os
import time
import json
import tempfile
import sqlite3
import pandas as pd
import smtplib
import urllib.parse
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai

# --- 1. CONFIG & CSS ---
st.set_page_config(
    page_title="Dastaavej - Property Safe Guard",
    page_icon="🏠",
    layout="centered"
)

st.markdown("""
<style>
    .blurred { filter: blur(5px); pointer-events: none; user-select: none; }
    .pay-wall-overlay {
        background-color: #f0f2f6; padding: 20px; border-radius: 10px;
        text-align: center; border: 2px solid #ff4b4b; margin-top: 20px;
    }
    .stage-card {
        padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0;
        margin-bottom: 10px; background-color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. BACKEND SETUP (Database & Email) ---
def init_db():
    conn = sqlite3.connect('dastavej_orders.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_no TEXT,
            doc_name TEXT,
            customer_name TEXT,
            contact_info TEXT,
            request_date TIMESTAMP,
            status TEXT,
            stage_context TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def log_request(doc_no, doc_name, name, contact, stage):
    conn = sqlite3.connect('dastavej_orders.db')
    c = conn.cursor()
    safe_doc_no = doc_no if doc_no else "MANUAL_SEARCH"
    c.execute('''
        INSERT INTO orders (doc_no, doc_name, customer_name, contact_info, request_date, status, stage_context)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (safe_doc_no, doc_name, name, contact, datetime.now(), 'Pending', stage))
    conn.commit()
    conn.close()

def update_order_status(order_id, new_status):
    conn = sqlite3.connect('dastavej_orders.db')
    c = conn.cursor()
    c.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    conn.commit()
    conn.close()

def send_confirmation_email(customer_email, customer_name, doc_name):
    if "gmail_user" in st.secrets:
        SENDER_EMAIL = st.secrets["gmail_user"]
        SENDER_PASSWORD = st.secrets["gmail_pass"]
    else:
        return False 

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = customer_email
        msg['Subject'] = f"Request Received: {doc_name}"

        body = f"""Hi {customer_name},\n\nWe received your request for: {doc_name}.\n\nOur team is verifying availability. We will contact you shortly.\n\n- Dastaavej Team"""
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        return False

# --- 3. POP-UP DIALOG (LEAD FORM) ---
@st.dialog("Get Expert Help")
def get_user_details(doc_no, doc_name, stage_context):
    st.write(f"**Item:** {doc_name}")
    if doc_no and doc_no != "N/A":
        st.caption(f"ID: {doc_no}")
    else:
        st.warning("Note: Manual Search Required")
    
    with st.form("entry_form"):
        name = st.text_input("Full Name")
        email = st.text_input("Email Address")
        phone = st.text_input("Phone Number")
        
        if st.form_submit_button("✅ Submit Request"):
            if name and email and phone:
                log_request(doc_no, doc_name, name, f"{phone} | {email}", stage_context)
                
                with st.spinner("Sending confirmation..."):
                    send_confirmation_email(email, name, doc_name)
                
                st.success("Request Sent! We will contact you shortly.")
                time.sleep(2)
                st.rerun()
            else:
                st.error("All fields are required.")

# --- 4. ADMIN DASHBOARD ---
def admin_dashboard():
    st.sidebar.markdown("---")
    st.sidebar.header("🔐 Admin Area")
    password = st.sidebar.text_input("Admin Password", type="password")
    
    if password == "admin123": 
        st.title("📋 Order Management")
        conn = sqlite3.connect('dastavej_orders.db')
        df = pd.read_sql_query("SELECT * FROM orders ORDER BY request_date DESC", conn)
        conn.close()

        df['status'] = df['status'].fillna('Pending')
        
        edited_df = st.data_editor(
            df, key="editor", hide_index=True, use_container_width=True,
            disabled=["id", "doc_no", "doc_name", "customer_name", "contact_info", "stage_context"]
        )
        st.caption("Type 'Completed' in status to update.")
        
        if st.button("💾 Save Changes"):
            for index, row in edited_df.iterrows():
                update_order_status(row['id'], row['status'])
            st.success("Updated!")
            time.sleep(1)
            st.rerun()

# --- 5. AI ENGINE (DYNAMIC PROMPTS) ---
def process_document(file_path, key, stage):
    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-flash-latest") 
    
    with st.spinner(f"🔍 AI is analyzing for '{stage}' risks..."):
        try:
            g_file = genai.upload_file(file_path)
            while g_file.state.name == "PROCESSING":
                time.sleep(1)
                g_file = genai.get_file(g_file.name)
        except Exception as e:
            return {"error": f"Upload Failed: {str(e)}"}
            
    # --- DYNAMIC PROMPT LOGIC ---
    base_structure = """
    {
      "property_summary": "Short location description",
      "current_owner": "Name",
      "risk_score": "Low/Medium/High",
      "analysis_summary": "2 sentences summarizing the overall safety of this deal.",
      "missing_docs_list": [
        {
            "year": "YYYY", 
            "doc_type": "Sale Deed/Will/Gift", 
            "doc_no": "str", 
            "reason": "Why is it missing?",
            "risk_explained": "Legal implication of missing this file."
        }
      ]
    }
    """
    
    if stage == "Negotiation":
        focus = "Focus on identifying VAGUE CLAUSES, undefined property schedules, or seller details that look suspicious. This is a preliminary draft check."
    elif stage == "Token Payment":
        focus = "Focus on THE CHAIN OF TITLE. Identify every single previous deed mentioned in the Recitals history that is NOT present in the file. These are critical gaps."
    else: # Loan Application
        focus = "Focus on BANKABILITY. stringent check. If the chain is not 100% complete (30 years), mark it as High Risk. Banks will reject incomplete chains."

    prompt = f"""
    Analyze this Property Document for a user in the '{stage}' stage.
    {focus}
    
    Return strictly valid JSON. Do not use Markdown.
    Structure: {base_structure}
    
    Rules: 
    1. If a document is mentioned in 'Recitals' (History) but NOT uploaded, it is MISSING.
    2. If doc_no is unknown, use "N/A".
    """
    
    try:
        response = model.generate_content([prompt, g_file])
        cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)
    except Exception as e:
        return {"error": f"AI Failed: {str(e)}"}

# --- 6. MAIN APP FLOW ---
with st.sidebar:
    st.success("✅ System Ready")
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        api_key = st.text_input("Enter Gemini API Key", type="password")
    admin_dashboard()

st.title("🏠 Dastaavej Gap Hunter")

# === STEP 1: STAGE SELECTION ===
st.subheader("Where are you in your buying journey?")
col1, col2, col3 = st.columns(3)

# Simple radio to select stage, formatted as "Cards" visually via columns if we wanted, 
# but Radio is safer for logic.
stage_selection = st.radio(
    "Select your current stage:",
    ["🔍 Negotiation / Just Looking", "💰 Paying Token Amount", "🏦 Applying for Loan"],
    horizontal=True,
    help="We customize the check based on your stage."
)

# Map selection to internal code
if "Negotiation" in stage_selection:
    current_stage = "Negotiation"
    upload_label = "Upload Broker Draft or Sale Deed"
    st.info("ℹ️ **Goal:** Check for red flags and vague clauses before you negotiate.")
elif "Token" in stage_selection:
    current_stage = "Token Payment"
    upload_label = "Upload Current Title Deed"
    st.info("ℹ️ **Goal:** Find missing historical links before you pay the advance.")
else:
    current_stage = "Loan Application"
    upload_label = "Upload All Available Deeds (Merged PDF)"
    st.error("ℹ️ **Goal:** Strict Bank-Level Verification. Zero tolerance for gaps.")

# === STEP 2: UPLOAD ===
uploaded_file = st.file_uploader(upload_label, type=["pdf"])

# Session State
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "is_paid" not in st.session_state:
    st.session_state.is_paid = False

# === STEP 3: ANALYZE ===
if st.button(f"Analyze for {current_stage}"):
    if not uploaded_file or not api_key:
        st.error("⚠️ Upload file and enter API Key.")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        result = process_document(tmp_path, api_key, current_stage)
        if "error" in result:
            st.error(result["error"])
        else:
            st.session_state.analysis_result = result
        os.remove(tmp_path)

# === STEP 4: RESULTS ===
if st.session_state.analysis_result:
    res = st.session_state.analysis_result
    st.divider()
    
    # Summary Section
    st.subheader(f"📊 {current_stage} Report")
    st.write(f"**Analysis:** {res.get('analysis_summary', 'Analysis Complete.')}")
    
    colA, colB = st.columns(2)
    colA.info(f"**Property:** {res.get('property_summary', 'N/A')}")
    colB.metric("Risk Score", res.get('risk_score', 'Unknown'))

    # The Gaps
    count = res.get('missing_docs_count', len(res.get('missing_docs_list', [])))
    
    if st.session_state.is_paid:
        # UNLOCKED VIEW
        st.subheader("🔓 Critical Issues Found")
        documents = res.get('missing_docs_list', [])
        
        if not documents:
            st.success("✅ No critical gaps found for this stage.")
        
        for i, doc in enumerate(documents):
            doc_no = doc.get('doc_no', 'N/A')
            doc_type = doc.get('doc_type', 'Unknown Doc')
            year = doc.get('year', '????')
            why_needed = doc.get('risk_explained', 'Critical for ownership.')
            
            with st.expander(f"⚠️ Issue: {year} {doc_type}"):
                st.write(f"**Reason:** {doc.get('reason')}")
                st.write(f"**Doc ID:** {doc_no}")
                st.info(f"💡 **Why:** {why_needed}")
                
                # HYBRID BUTTONS
                if doc_no and doc_no != 'N/A':
                    if st.button(f"Request Copy (₹499)", key=f"btn_buy_{i}"):
                        get_user_details(doc_no, f"ORDER [{current_stage}]: {year} {doc_type}", current_stage)
                else:
                    if st.button(f"🔍 Check Availability (Free)", key=f"btn_check_{i}", type="primary"):
                        get_user_details("N/A", f"INQUIRY [{current_stage}]: {year} {doc_type}", current_stage)

    elif count > 0:
        # LOCKED VIEW
        st.error(f"⚠️ Found {count} Risks affecting your {current_stage}.")
        
        st.markdown(f"""
        <div class="pay-wall-overlay">
            <h3>⚠️ Reveal {count} Hidden Risks</h3>
            <p>Don't proceed with {current_stage} blindly.</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🔓 Unlock Report for ₹99"):
            with st.spinner("Processing Payment..."):
                time.sleep(1)
                st.session_state.is_paid = True
                st.rerun()
    else:
        st.success(f"✅ Your {current_stage} check looks clean!")
import streamlit as st
import os
import time
import json
import tempfile

# --- 1. PAGE CONFIG & CSS (Must be first) ---
st.set_page_config(
    page_title="Dastaavej Gap Hunter",
    page_icon="🏠",
    layout="centered"
)

# CSS for the "Blur" effect and Paywall styling
st.markdown("""
<style>
    .blurred {
        filter: blur(5px);
        pointer-events: none;
        user-select: none;
    }
    .pay-wall-overlay {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        border: 2px solid #ff4b4b;
        margin-top: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. LEGAL DISCLAIMER (The Shield) ---
if "agreed" not in st.session_state:
    st.session_state.agreed = False

if not st.session_state.agreed:
    st.warning("⚠️ LEGAL DISCLAIMER")
    st.markdown("""
    **Please read before proceeding:**
    1. This tool uses AI to analyze documents. **It is NOT a lawyer.**
    2. AI can make errors ("hallucinations").
    3. Dastaavej is not liable for any financial decisions you make.
    """)
    if st.button("I Understand & Accept Risks"):
        st.session_state.agreed = True
        st.rerun()
    st.stop() # Stops app here until agreed

# --- 3. UI SETUP ---
st.title("🏠 Dastaavej Gap Hunter")
st.markdown("### Upload a Sale Deed to check for missing history.")

with st.sidebar:
    st.success("✅ System Ready")
    api_key = st.text_input("Enter Gemini API Key", type="password")
    st.info("Your key is never stored.")

uploaded_file = st.file_uploader("Upload Property Document (PDF)", type=["pdf"])

# Initialize Session State for Results (So they don't vanish on reload)
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "is_paid" not in st.session_state:
    st.session_state.is_paid = False

# --- 4. THE LOGIC (Your Stable Version + Safety Filters) ---
# --- 4. THE ROBUST LOGIC (Fixed Model + Error Handling) ---
def process_document(file_path, key):
    import google.generativeai as genai
    
    genai.configure(api_key=key)
    
    # SAFETY: Force the model to ignore "sensitive" legal content
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    
    # CRITICAL FIX: Using the Experimental model because it worked for you previously
    # whereas 1.5-flash and 2.0-flash gave "Quota: 0" errors.
    model = genai.GenerativeModel(
        "gemini-flash-latest", 
        safety_settings=safety_settings
    )
    
    with st.spinner("🔍 AI is analyzing the Chain of Title..."):
        try:
            g_file = genai.upload_file(file_path)
            while g_file.state.name == "PROCESSING":
                time.sleep(1)
                g_file = genai.get_file(g_file.name)
        except Exception as e:
            return {"error": f"File Upload Failed: {str(e)}"}
            
    prompt = """
    Analyze this Property Deed. 
    Return strictly valid JSON. Do not use Markdown. Do not use ```json.
    Structure:
    {
      "property_summary": "Short location description",
      "current_owner": "Name",
      "missing_docs_count": 0,
      "missing_docs_list": [{"year": "YYYY", "doc_type": "str", "doc_no": "str", "reason": "str"}],
      "risk_score": "Low/Medium/High"
    }
    Rules: If a document is mentioned in 'Recitals' history but NOT uploaded, it is MISSING.
    """
    
    response = None # Initialize variable to prevent UnboundLocalError
    
    try:
        response = model.generate_content([prompt, g_file])
        raw_text = response.text
        
        # CLEANER: Remove markdown if present
        cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        return json.loads(cleaned_text)
        
    except Exception as e:
        # Debug helper: print what the AI actually said if it failed
        debug_info = ""
        if response:
            debug_info = f" | Raw Output: {response.text}"
            
        return {"error": f"AI Processing Failed: {str(e)}{debug_info}"}
# --- 5. EXECUTION & PAYWALL LOGIC ---
if st.button("Analyze Gap Report"):
    if not uploaded_file or not api_key:
        st.error("⚠️ Please upload file and enter API Key.")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        try:
            result = process_document(tmp_path, api_key)
            if "error" in result:
                st.error("AI Error: " + result["error"])
            else:
                st.session_state.analysis_result = result
        finally:
            os.remove(tmp_path)

# --- 6. DISPLAY RESULTS (The Money Maker) ---
if st.session_state.analysis_result:
    res = st.session_state.analysis_result
    
    st.divider()
    
    # FREE DATA (The Hook)
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Property:** {res.get('property_summary', 'N/A')}")
    with col2:
        st.success(f"**Owner:** {res.get('current_owner', 'N/A')}")

    # THE SCARE (Value Prop)
    count = res.get('missing_docs_count', 0)
    if count > 0:
        st.error(f"⚠️ DANGER: We found {count} MISSING Documents in the history.")
    else:
        st.success("✅ Chain appears clean.")

    # PAYWALL SECTION
    if st.session_state.is_paid:
        # == UNLOCKED VIEW ==
        st.subheader("🔓 Full Gap Checklist")
        st.write(f"**Risk Level:** {res.get('risk_score')}")
        
        for doc in res.get('missing_docs_list', []):
            with st.expander(f"❌ Missing: {doc['year']} {doc['doc_type']}"):
                st.write(f"**Document #:** {doc['doc_no']}")
                st.write(f"**Reason:** {doc['reason']}")
                st.button("Request Copy (₹499)", key=doc['doc_no'])
    
    elif count > 0:
        # == LOCKED VIEW (The Blur) ==
        st.subheader("🔒 Detailed Report")
        
        # Fake blurred content to tease the user
        st.markdown("""
        <div class="blurred">
        <h4>1. Missing: 1995 Sale Deed (Doc #*****)</h4>
        <p>Critical root title document...</p>
        <hr>
        <h4>2. Missing: 2004 Rectification Deed</h4>
        </div>
        """, unsafe_allow_html=True)
        
        # The Pay Button
        st.markdown(f"""
        <div class="pay-wall-overlay">
            <h3>⚠️ Reveal {count} Critical Gaps</h3>
            <p>Protect your ₹50 Lakh investment.</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🔓 Unlock Report for ₹99"):
            with st.spinner("Processing Payment..."):
                time.sleep(1)
                st.session_state.is_paid = True
                st.rerun()
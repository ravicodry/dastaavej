import streamlit as st
import os
import time
import json
import tempfile

# --- 1. PAGE CONFIG (Must be the very first command) ---
st.set_page_config(
    page_title="Dastaavej Gap Hunter",
    page_icon="🏠",
    layout="centered"
)

# --- DEBUG CHECK ---
# If you see this in the sidebar, the app has loaded successfully.
with st.sidebar:
    st.success("✅ App Interface Loaded")
    api_key = st.text_input("Enter Gemini API Key", type="password")
    st.info("Get your key from Google AI Studio")

    with st.expander("Debug: List Models"):
        if st.button("List Available Models"):
            if api_key:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    models = list(genai.list_models())
                    st.write([m.name for m in models if 'generateContent' in m.supported_generation_methods])
                except Exception as e:
                    st.error(f"Error listing models: {e}")
            else:
                st.error("Enter API Key first")

# --- MAIN UI ---
st.title("🏠 Dastaavej Gap Hunter")
st.markdown("### Upload a Sale Deed to check for missing history.")

uploaded_file = st.file_uploader("Upload Property Document (PDF)", type=["pdf"])

# --- THE LOGIC (Modified for Stability) ---
# --- 3. THE LOGIC (With Auto-Retry Fix) ---
def process_document(file_path, key):
    import google.generativeai as genai
    from google.api_core import exceptions
    
    genai.configure(api_key=key)
    # 1.5 Flash is the ONLY model reliable on Free Tier right now
    model = genai.GenerativeModel("gemini-flash-latest") 
    
    # Upload with a wait loop
    with st.spinner("Encrypting and uploading to AI secure vault..."):
        g_file = genai.upload_file(file_path)
        while g_file.state.name == "PROCESSING":
            time.sleep(1)
            g_file = genai.get_file(g_file.name)
            
    # The Prompt
    prompt = """
    Extract the history of ownership from this deed. 
    Return JSON: {"current_doc": "str", "missing_docs": [{"year": "str", "doc_type": "str", "reason": "str"}]}
    """
    
    # RETRY LOGIC: If we hit a rate limit, we wait and try once more
    try:
        response = model.generate_content([prompt, g_file])
        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            st.error("🤖 AI returned invalid JSON. Raw response:")
            st.code(response.text)
            return {"current_doc": "Error", "missing_docs": []}
            
    except exceptions.ResourceExhausted:
        # If we hit the speed limit (429)
        st.warning("⚠️ High traffic on Free Tier. Waiting 10 seconds to retry...")
        time.sleep(10)
        # Try one last time
        response = model.generate_content([prompt, g_file])
        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            st.error("🤖 AI returned invalid JSON (after retry). Raw response:")
            st.code(response.text)
            return {"current_doc": "Error", "missing_docs": []}

# --- EXECUTION BUTTON ---
if st.button("Analyze Gap Report"):
    if not uploaded_file:
        st.error("⚠️ Please upload a PDF first.")
    elif not api_key:
        st.error("⚠️ Please enter your API Key in the sidebar.")
    else:
        # WINDOWS-SAFE TEMP FILE HANDLING
        # We create a file, write to it, and CLOSE it immediately.
        # This prevents "Permission Denied" errors on Windows.
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
            
            # Now the file is closed, we can pass the PATH to the function
            result = process_document(tmp_path, api_key)
            
            # --- DISPLAY ---
            st.divider()
            st.subheader(f"📄 Result: {result['current_doc']}")
            
            if result['missing_docs']:
                for doc in result['missing_docs']:
                    st.error(f"❌ MISSING: {doc['year']} {doc['doc_type']}")
            else:
                st.success("✅ No gaps found!")

        except Exception as e:
            st.error(f"Error: {e}")
        
        finally:
            # Clean up the temp file
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
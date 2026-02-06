
import streamlit as st
import pandas as pd
from reviewer import ReviewEngine

st.set_page_config(page_title="Code Review Platform POC", layout="wide")

def main():
    st.title("🛡️ Code Review Platform POC")
    st.markdown("### Automated & AI-Powered Code Review for Data Engineering")

    # Sidebar Configuration
    with st.sidebar:
        st.header("Configuration")
        
        # AI Provider Selection
        ai_provider = st.selectbox("Select AI Provider", ["OpenAI", "Gemini"])
        
        api_key = st.text_input(f"{ai_provider} API Key", type="password", help="Required for AI insights")
        
        st.divider()
        st.subheader("Review Scope")
        focus_cdl = st.checkbox("Focus on 'Code CDL Standards'", value=True)
        
        st.divider()
        st.info("Checklist loaded from `checklist.csv`")
        if st.checkbox("View Raw Checklist"):
            try:
                st.dataframe(pd.read_csv("checklist.csv"))
            except:
                st.error("checklist.csv not found")

    # Initialize Engine
    engine = ReviewEngine("checklist.csv", ai_provider=ai_provider, ai_api_key=api_key)

    # Main Input Area
    st.subheader("1. Input Code")
    
    input_method = st.radio("Select Input Method:", ("Paste Code", "Upload File"), horizontal=True)
    code_content = ""
    
    if input_method == "Paste Code":
        code_content = st.text_area("Paste your PySpark/Python code here:", height=300)
    else:
        uploaded_file = st.file_uploader("Upload .py or .ipynb file", type=["py", "txt"])
        if uploaded_file is not None:
             try:
                stringio = uploaded_file.getvalue().decode("utf-8")
                code_content = stringio
             except Exception as e:
                st.error(f"Error reading file: {e}")

    # Operations
    if st.button("🚀 Run Smart Review", type="primary", disabled=not code_content.strip()):
        filter_cat = "Code CDL Standards" if focus_cdl else None
        run_analysis(engine, code_content, filter_cat)

def run_analysis(engine, code, filter_cat):
    st.divider()
    st.subheader("2. Review Report")
    
    with st.spinner("Running AST Analysis & AI Agents..."):
        results = engine.analyze(code, filter_category=filter_cat)
        
    automated_findings = results.get("automated_results", [])
    ai_findings = results.get("ai_results", [])
    manual_checklist = results.get("manual_checklist", [])
    
    # 1. Static Analysis (AST)
    st.markdown("#### 🔍 Static Analysis (AST)")
    if automated_findings:
        for finding in automated_findings:
            color = "red" if finding['status'] == 'Fail' else "orange" if finding['status'] == 'Warning' else "blue"
            st.markdown(f"**Line {finding['line']}**: :{color}[{finding['status']}] - {finding['message']}")
    else:
        st.success("No static issues found.")

    st.divider()

    # 2. AI Insights
    st.markdown("#### 🤖 AI Insights")
    if ai_findings:
        for finding in ai_findings:
            icon = "✅" if finding['status'] == 'Pass' else "❌"
            st.markdown(f"**{icon} {finding['status']}**: {finding['check']}")
            st.caption(f"Reasoning: {finding['message']}")
    else:
        if not manual_checklist:
             st.info("AI had no specific comments (or logic covered by manual check).")
        else:
             st.warning("AI Insights unavailable or skipped (Check API Key).")

    st.divider()
    
    # 3. Manual Review
    st.subheader("3. Manual Verification Needed")
    st.caption("Items where AI was unsure or static analysis check doesn't exist.")
    
    if manual_checklist:
        for item in manual_checklist:
            with st.expander(f"📋 {item['Description']}", expanded=True):
                st.write(f"**Category:** {item['Category']}")
                if item.get("AI_Note"):
                    st.info(f"AI Note: {item['AI_Note']}")
                st.checkbox("Mark as Verified", key=f"manual_{item['Description'][:20]}")
    else:
        st.success("All checklist items covered by Automated/AI checks!")

if __name__ == "__main__":
    main()

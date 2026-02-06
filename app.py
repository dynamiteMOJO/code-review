import streamlit as st
import pandas as pd
from reviewer import ReviewEngine

st.set_page_config(page_title="Code Review", layout="wide")

def render_header():
    st.markdown("""
    <style>
        /* Hide default Streamlit header */
        header[data-testid="stHeader"] {
            display: none !important;
        }

        /* Fixed full-width header on top of everything */
        .fixed-header {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 60px;
            z-index: 999999;
            background-color: var(--background-color); 
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            padding: 0 20px;
            color: var(--text-color); /* Automatically handles Light/Dark mode */
            overflow: visible;
        }
        
        /* Force sidebar to start below header */
        [data-testid="stSidebar"] {
            top: 60px !important;
            height: calc(100vh - 60px) !important;
            z-index: 1000;
        }

        /* Adjust main content area to avoid overlap */
        .main-spacer {
            height: 70px;
        }

        /* Header content layout */
        .header-content {
            display: flex;
            align-items: center;
            gap: 15px;
            white-space: nowrap;
        }
        
        .header-content h2 {
            margin: 0 !important;
            font-weight: 600;
            color: var(--text-color);
            line-height: 1.2;
            font-size: 1.8rem;
        }

        /* Logo styling to handle both modes */
        .UnityLogo svg {
            fill: currentColor; /* Inherits var(--text-color) */
        }

    </style>
    
    <div class="fixed-header">
        <div class="header-content">
            <span class="UnityLogo">
                <svg viewBox="0 0 138 24" height="24" xmlns="http://www.w3.org/2000/svg" alt="abbvie logo">
                    <path d="M137.37 23.2343C137.37 21.7834 136.524 21.2595 135.134 21.2595H124.574C119.617 21.2595 117.864 18.1965 117.642 16.0806H132.292C136.564 16.0806 137.834 12.9975 137.834 11.0227C137.834 8.90679 136.463 5.96473 132.292 5.96473H124.373C117.159 5.96473 114.801 10.8615 114.801 14.8514C114.801 19.2242 117.501 23.738 124.353 23.738H137.37V23.2343ZM124.595 8.44331H131.93C134.468 8.44331 135.073 10.0151 135.073 11.0428C135.073 11.9496 134.509 13.6423 131.93 13.6423H117.642C117.824 11.8489 119.295 8.44331 124.595 8.44331ZM94.7103 22.6096C93.9648 23.6373 93.4408 24 92.7759 24C91.8488 24 91.5062 23.4962 90.8413 22.6096C89.2493 20.4332 78.6499 5.96473 78.6499 5.96473H80.2821C82.0555 5.96473 82.5591 6.58942 83.2847 7.61714C83.6069 8.06044 92.8161 21.0579 92.8161 21.0579C92.8161 21.0579 102.025 8.08059 102.388 7.55668C103.073 6.58942 103.597 5.96473 105.37 5.96473H106.801C106.801 5.96473 96.0202 20.8363 94.7103 22.6096ZM25.2292 23.738C24.1209 23.738 23.4156 23.1939 23.2141 22.005L22.8514 20.0705C22.2469 21.1788 20.0302 23.738 15.2141 23.738H9.67254C2.13602 23.738 0 18.6196 0 14.8514C0 10.5995 2.5592 5.96473 9.67254 5.96473H15.2141C20.6146 5.96473 23.597 9.10831 24.3224 12.937C24.927 16.1411 26.3375 23.738 26.3375 23.738H25.2292ZM14.5894 8.44331H9.8539C4.53401 8.44331 2.7204 11.8287 2.7204 14.8514C2.7204 17.8741 4.53401 21.2595 9.8539 21.2595H14.5894C20.1511 21.2595 21.7632 17.733 21.7632 14.8514C21.7632 12.272 20.3123 8.44331 14.5894 8.44331ZM110.408 3.92948C111.194 3.92948 111.799 3.44585 111.799 2.51889V1.93451C111.799 1.00756 111.174 0.523931 110.408 0.523931C109.642 0.523931 109.018 0.987405 109.018 1.93451V2.51889C108.998 3.44585 109.622 3.92948 110.408 3.92948ZM109.038 5.96473H109.683C110.952 5.96473 111.758 6.52897 111.758 8.26195V23.738H111.073C109.683 23.738 109.018 22.9924 109.018 21.5013C109.038 21.2796 109.038 5.96473 109.038 5.96473ZM30.5089 8.2821C31.6775 7.17381 33.7734 5.96473 37.0781 5.96473H42.6196C50.156 5.96473 52.2922 11.0831 52.2922 14.8514C52.2922 19.1033 49.7329 23.738 42.6196 23.738H37.0781C31.6775 23.738 27.7884 20.2519 27.7884 14.8514V0H28.6347C29.8438 0 30.5089 0.624684 30.5089 1.75315V8.2821ZM37.6826 21.2595H42.4181C47.7382 21.2595 49.5515 17.8741 49.5515 14.8514C49.5515 11.8287 47.7382 8.44331 42.4181 8.44331H37.6826C32.1208 8.44331 30.5089 11.9698 30.5089 14.8514C30.5089 17.4307 31.9397 21.2595 37.6826 21.2595ZM57.7532 8.2821C58.922 7.17381 61.0176 5.96473 64.3223 5.96473H69.8641C77.4005 5.96473 79.5364 11.0831 79.5364 14.8514C79.5364 19.1033 76.9774 23.738 69.8641 23.738H64.3223C58.922 23.738 55.0329 20.2519 55.0329 14.8514V0H55.8792C57.0883 0 57.7532 0.624684 57.7532 1.75315V8.2821ZM64.9269 21.2595H69.6626C74.9824 21.2595 76.796 17.8741 76.796 14.8514C76.796 11.8287 74.9824 8.44331 69.6626 8.44331H64.9269C59.3653 8.44331 57.7532 11.9698 57.7532 14.8514C57.7532 17.4307 59.204 21.2595 64.9269 21.2595Z" />
                </svg>
            </span>
            <span style="font-size: 20px; color: #666; font-weight: 600;">|</span>
            <h2 style="margin: 0; font-weight: 600;">Code Review</h2>
        </div>
    </div>
    <div class="main-spacer"></div>
    """, unsafe_allow_html=True)

def render_report_page(engine):
    # Back button
    col1, col2 = st.columns([1, 10])
    with col1:
        if st.button("← Back"):
            st.session_state.page = "input"
            st.session_state.start_review = False
            st.rerun()
    
    st.divider()
    st.subheader("2. Review Report")
    
    # Placeholders for streaming content
    status_placeholder = st.empty()
    results_placeholder = st.empty()
    
    if st.session_state.get("start_review", False):
        st.session_state.start_review = False 
        
        st.session_state.review_results = []
        status_placeholder.info("Running Analysis...")
        
        code = st.session_state.get("review_code", "")
        lang = st.session_state.get("review_language", "python")
        cat = st.session_state.get("review_category", None)
        
        try:
            for result in engine.analyze_stream(code, filter_category=cat, language=lang):
                # Format result for display
                review_comment = result['comment']
                line_info = f"(Line: {result['line_number']})" if result['line_number'] != "General" else ""
                full_review = f"{review_comment} {line_info}"
                
                # Add icons to status
                status_map = {
                    "Pass": "✅ Pass",
                    "Fail": "❌ Fail",
                    "Warning": "⚠️ Warning",
                    "Unsure": "❓ Unsure",
                    "Info": "ℹ️ Info"
                }
                status_with_icon = status_map.get(result["status"], result["status"])
                
                check_item = {
                    "Checklist Item": result["checklist_item"],
                    "Review": full_review,
                    "Confidence": result["confidence"],
                    "Status": status_with_icon
                }
                
                st.session_state.review_results.append(check_item)
                
                # Update DataFrame
                df = pd.DataFrame(st.session_state.review_results)
                # Force column order
                df = df[["Checklist Item", "Review", "Confidence", "Status"]]
                
                results_placeholder.dataframe(
                    df, 
                    use_container_width=True, 
                    hide_index=True
                )
            
            status_placeholder.success("Review Complete!")
            
        except Exception as e:
            status_placeholder.error(f"Error during review: {str(e)}")
            
    else:
        # Show existing results
        if st.session_state.get("review_results"):
            df = pd.DataFrame(st.session_state.review_results)
            
            # Ensure order even on reload (if columns exist)
            cols = ["Checklist Item", "Review", "Confidence", "Status"]
            if all(col in df.columns for col in cols):
                 df = df[cols]
            
            results_placeholder.dataframe(
                df, 
                use_container_width=True, 
                hide_index=True
            )
        else:
            status_placeholder.info("No active review. Go back and submit code.")


def render_input_page(engine, focus_cdl):
    st.subheader("1. Input Code")
    
    input_method = st.radio("Select Input Method:", ("Paste Code", "Upload File"), horizontal=True)
    code_content = ""
    language = "python" # default

    if input_method == "Paste Code":
        language = st.selectbox("Select Language", ["python", "sql", "hql", "jil"])
        code_content = st.text_area(f"Paste your {language} code here:", height=300, key="input_code_area")
    else:
        uploaded_file = st.file_uploader("Upload .py, .sql, .hql, .jil file", type=["py", "txt", "sql", "hql", "jil"])
        if uploaded_file is not None:
             try:
                stringio = uploaded_file.getvalue().decode("utf-8")
                code_content = stringio
                
                # Determine language from extension
                filename = uploaded_file.name.lower()
                if filename.endswith(".sql"):
                    language = "sql"
                elif filename.endswith(".hql"):
                    language = "hql" # HiveQL
                elif filename.endswith(".jil"):
                    language = "jil"
                else:
                    language = "python"
                    
             except Exception as e:
                st.error(f"Error reading file: {e}")

    # Operations
    if st.button("Run Review", type="primary", disabled=not code_content.strip()):
        st.session_state.review_code = code_content
        st.session_state.review_language = language
        st.session_state.review_category = "Code CDL Standards" if focus_cdl else None
        st.session_state.start_review = True
        st.session_state.page = "report"
        st.rerun()

def main():
    if "page" not in st.session_state:
        st.session_state.page = "input"
    
    # Ensure session state variables exist
    if "review_results" not in st.session_state:
        st.session_state.review_results = []

    render_header()
    
    st.divider()

    # Sidebar Configuration
    with st.sidebar:
        st.header("Configuration")
        
        # AI Provider Selection
        ai_provider = st.selectbox("Select Provider", ["anthropic", "openai"])
        
        # Dynamic Model Default
        default_model = "gpt-4" if ai_provider == "openai" else "claude-sonnet-4-5-20250929"
        model_name = st.text_input("AI Model Name", value=default_model)
        
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

    # Initialize Engine (No API Key needed from UI)
    engine = ReviewEngine("checklist.csv", ai_provider=ai_provider, ai_model=model_name)

    if st.session_state.page == "input":
        render_input_page(engine, focus_cdl)
    elif st.session_state.page == "report":
        render_report_page(engine)

if __name__ == "__main__":
    main()

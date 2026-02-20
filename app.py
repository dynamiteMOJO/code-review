import streamlit as st
import pandas as pd
from reviewer import ReviewEngine
from github_client import GitHubClient
import html
import os
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.formatters.html import HtmlFormatter
import re
import time

import sqlite3
import re

# Helper functions for highlighting
def tokenize_html(html_line):
    """
    Tokenizes HTML into (type, value, length) tuples.
    types: 'tag', 'entity', 'text'
    """
    tokens = []
    # Regex to capture: tags, entities, or generic text
    # Note: Text might contain < or & if strictly trying to not match bad HTML, 
    # but we assume valid fragments from Pygments.
    # Group 1: tag, Group 2: entity, Group 3: text
    pattern = re.compile(r'(<[^>]+>)|(&[^;]+;)|([^<&]+)')
    
    for match in pattern.finditer(html_line):
        if match.group(1):
            tokens.append(('tag', match.group(1), 0)) # length 0 for plain text value
        elif match.group(2):
            # For entity, we need its decoded length
            decoded = html.unescape(match.group(2))
            tokens.append(('entity', match.group(2), len(decoded)))
        else:
            text = match.group(3)
            tokens.append(('text', text, len(text)))
    return tokens

def inject_highlight(html_line, substring, status_class):
    """
    Injects highlight by tokenizing HTML and wrapping content intersect.
    """
    try:
        if not substring:
            return html_line
            
        tokens = tokenize_html(html_line)
        
        # Build plain text to find substring
        plain_text = ""
        for t_type, t_val, t_len in tokens:
            if t_type == 'text':
                plain_text += t_val
            elif t_type == 'entity':
                plain_text += html.unescape(t_val)
                
        # Find start/end
        start_idx = plain_text.find(substring)
        if start_idx == -1:
            return html_line
        end_idx = start_idx + len(substring)
        
        # Reconstruct
        new_html = []
        current_idx = 0
        
        for t_type, t_val, t_len in tokens:
            if t_type == 'tag':
                new_html.append(t_val)
                continue
                
            # Content or Entity
            token_end = current_idx + t_len
            
            # Check overlap
            overlap_start = max(current_idx, start_idx)
            overlap_end = min(token_end, end_idx)
            
            if overlap_start < overlap_end:
                # There is overlap
                if t_type == 'entity':
                    # Can't split entity, wrap whole if ANY overlap (simplification)
                    # Or only if full overlap? Let's wrap whole.
                    new_html.append(f'<span class="highlight-marker {status_class}">{t_val}</span>')
                else:
                    # Text - might need splitting
                    # Relative indices in the token string make no sense if we use indices based on plain text
                    # We need rel_start and rel_end inside the token's string
                    rel_start = overlap_start - current_idx
                    rel_end = overlap_end - current_idx
                    
                    pre = t_val[:rel_start]
                    mid = t_val[rel_start:rel_end]
                    post = t_val[rel_end:]
                    
                    if pre: new_html.append(pre)
                    new_html.append(f'<span class="highlight-marker {status_class}">{mid}</span>')
                    if post: new_html.append(post)
            else:
                # No overlap
                new_html.append(t_val)
                
            current_idx += t_len
            
        return "".join(new_html)
        
    except Exception as e:
        # print(f"Highlight error: {e}")
        return html_line

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

def generate_highlighted_code(code, findings, language='python'):
    # precise colors for the border/gutter - more prominent
    status_colors = {
        "Pass": "transparent",
        "Fail": "#e53e3e",    # Red
        "Warning": "#dd6b20", # Orange
        "Unsure": "#3182ce",  # Blue
        "Info": "#718096"     # Gray
    }
    
    # subtle background tints - kept for line background if needed, but we will use them for substring highlighting now
    bg_colors = {
        "Pass": "transparent",
        "Fail": "rgba(249, 38, 114, 0.25)",
        "Warning": "rgba(253, 151, 31, 0.25)", 
        "Unsure": "rgba(102, 217, 239, 0.25)", 
        "Info": "rgba(166, 226, 46, 0.25)"   
    }

    border_colors = {
        "Fail": "#f92672",
        "Warning": "#fd971f",
        "Unsure": "#66d9ef",
        "Info": "#a6e22e"
    }
    
    # Map line numbers
    findings_map = {}
    for finding in findings:
        line_num = str(finding.get('line_number', ''))
        if not line_num or line_num.lower() == "general":
            continue
        try:
            parts = line_num.split('-')
            start = int(parts[0])
            end = int(parts[1]) if len(parts) > 1 else start
            for i in range(start, end + 1):
                if i not in findings_map:
                    findings_map[i] = []
                findings_map[i].append(finding)
        except (ValueError, IndexError):
            continue

    # Get Pygments Lexer
    try:
        lexer = get_lexer_by_name(language, stripall=False)
    except:
        lexer = guess_lexer(code)
        
    formatter = HtmlFormatter(style='monokai', nowrap=True, noclasses=True)
    
    # We need to highlight line by line to inject our custom wrappers
    # But highlighting line by line breaks multi-line tokens (like docstrings).
    # So we highlight the whole block, then split.
    highlighted_code = highlight(code, lexer, formatter)
    
    # Split by newline (handling different newline types if needed, but usually \n)
    # create a list of spans
    code_lines = highlighted_code.splitlines()

# Re-assemble with line numbers and status indicators
    html_rows = []

    # Container Style

    # Container Style
    html_rows.append('''
<style>
    .code-container {
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 14px;
        background-color: #272822; /* Monokai background */
        color: #f8f8f2;           /* Monokai foreground */
        border: 1px solid #48483e;
        border-radius: 6px;
        overflow: hidden;
    }
    .code-row {
        display: flex;
        width: 100%;
        line-height: 1.5;
        transition: background-color 0.1s ease;
    }
    .code-row:hover {
        background-color: rgba(255, 255, 255, 0.05);
    }
    .line-num {
        min-width: 45px;
        text-align: right;
        padding-right: 12px;
        padding-left: 8px;
        color: #85816e; /* Slightly brighter Monokai comment */
        background-color: #2e2f29; /* Slightly distinct from code area */
        border-right: 1px solid #48483e;
        user-select: none;
        font-size: 12px;
    }
    .code-content {
        flex-grow: 1;
        padding-left: 15px;
        white-space: pre;
        overflow-x: auto;
    }
    /* Specific statuses - Adjusted for Dark Mode */
    /* Only border, no full background for line */
    .status-Fail { border-left: 4px solid #f92672; }
    .status-Warning { border-left: 4px solid #fd971f; }
    .status-Unsure { border-left: 4px solid #66d9ef; }
    .status-Info { border-left: 4px solid #a6e22e; }
    .status-Pass { border-left: 4px solid transparent; }
    
    .highlight-marker {
        border-radius: 2px;
        padding: 1px 0;
        position: relative;
    }
    
    .hl-Fail { 
        background-color: rgba(249, 38, 114, 0.2);
        border-bottom: 3.5px wavy #f92672;
    }
    .hl-Warning { 
        background-color: rgba(253, 151, 31, 0.2);
        border-bottom: 3.5px wavy #fd971f;
    }
    .hl-Unsure { 
        background-color: rgba(102, 217, 239, 0.2);
        border-bottom: 3.5px dotted #66d9ef;
    }
    .hl-Info { 
        background-color: rgba(166, 226, 46, 0.2);
        border-bottom: 2.5px dashed #a6e22e;
    }
    
    .tooltip {
        position: relative;
        cursor: help;
    }
</style>
<div class="code-container">
''')
    
    # Ensure code_lines length matches line count (handling trailing newline edge case if splitlines drops it)
    total_lines = len(code.splitlines())
    if len(code_lines) < total_lines:
        code_lines.append("") # Pad if needed

    for i, line_html in enumerate(code_lines, 1):
        status_class = "status-Pass"
        tooltip_attr = ""
        
        if i in findings_map:
            line_findings = findings_map[i]
            statuses = [] # We will collect confirmed statuses
            
            # Tooltip
            tips = []
            for f in line_findings:
                # Check if this finding actually applies to this line visually
                should_show = False
                
                # Try precise highlighting if substring is available
                sub = f.get('substring', '').strip()
                if sub:
                    # Use deterministic offset mapping
                    status = f['status']
                    hl_class = f"hl-{status}"
                    
                    # Apply highlight
                    new_line_html = inject_highlight(line_html, sub, hl_class)
                    if new_line_html != line_html:
                        line_html = new_line_html
                        should_show = True
                else:
                    # No substring -> applies to the whole range
                    should_show = True
                
                if should_show:
                    statuses.append(f['status'])
                    tips.append(f"[{f['status']}] {f['checklist_item']}:\n{f['comment']}")

            if statuses:
                # Priority: Fail > Warning > Unsure > Info
                if "Fail" in statuses:
                    status_class = "status-Fail"
                elif "Warning" in statuses:
                    status_class = "status-Warning"
                elif "Unsure" in statuses:
                    status_class = "status-Unsure"
                elif "Info" in statuses:
                    status_class = "status-Info"
                
                tooltip_text = "\n\n".join(tips)
                # Escape HTML and replace newlines with &#10; to keep the attribute valid and multiline in browser
                escaped_tooltip = html.escape(tooltip_text).replace('\n', '&#10;')
                tooltip_attr = f'title="{escaped_tooltip}"'
            
        row_html = f'''
<div class="code-row {status_class}" {tooltip_attr}>
    <div class="line-num">{i}</div>
    <div class="code-content">{line_html}</div>
</div>
'''
        html_rows.append(row_html)

    html_rows.append('</div>')
    
    return "".join(html_rows)

def _render_summary_card(summary_md: str, findings: list):
    """Render the Review Summary as a styled card above the tabs."""
    fail_count = sum(1 for f in findings if f.get('status') == 'Fail')
    warn_count = sum(1 for f in findings if f.get('status') == 'Warning')
    pass_count = sum(1 for f in findings if f.get('status') == 'Pass')

    if fail_count > 0:
        badge_color = "#e53e3e"
        badge_text = f"❌ {fail_count} Critical Issue{'s' if fail_count > 1 else ''}"
        card_border = "#e53e3e"
    elif warn_count > 0:
        badge_color = "#dd6b20"
        badge_text = f"⚠️ {warn_count} Warning{'s' if warn_count > 1 else ''}"
        card_border = "#dd6b20"
    else:
        badge_color = "#38a169"
        badge_text = "✅ Looks Good"
        card_border = "#38a169"

    st.markdown(f"""
    <style>
        .summary-card {{
            border-left: 5px solid {card_border};
            background: linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%);
            border-radius: 8px;
            padding: 18px 24px 14px 24px;
            margin-bottom: 18px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.10);
        }}
        .summary-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }}
        .summary-title {{
            font-size: 1.15rem;
            font-weight: 700;
            letter-spacing: 0.01em;
        }}
        .summary-badge {{
            background-color: {badge_color};
            color: white;
            border-radius: 20px;
            padding: 2px 14px;
            font-size: 0.82rem;
            font-weight: 600;
            white-space: nowrap;
        }}
        .summary-stats {{
            display: flex;
            gap: 16px;
            margin-top: 4px;
            font-size: 0.82rem;
            color: #888;
        }}
        .stat-chip {{
            background: rgba(255,255,255,0.07);
            border-radius: 12px;
            padding: 2px 10px;
        }}
    </style>
    <div class="summary-card">
        <div class="summary-header">
            <span class="summary-title">📋 Review Summary</span>
            <span class="summary-badge">{badge_text}</span>
        </div>
        <div class="summary-stats">
            <span class="stat-chip">❌ {fail_count} Fail</span>
            <span class="stat-chip">⚠️ {warn_count} Warning</span>
            <span class="stat-chip">✅ {pass_count} Pass</span>
            <span class="stat-chip">🔍 {len(findings)} Total Checks</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(summary_md)
    st.divider()


def _render_recommendations_tab(engine):
    """Render the AI Recommended Checklist Items tab with checkboxes and add-to-DB support."""
    findings = st.session_state.get("review_findings", [])
    code = st.session_state.get("review_code", "")
    lang = st.session_state.get("review_language", "python")

    if not findings:
        st.info("Run a review first to see recommendations.")
        return

    # Load or generate recommendations (cached in session state)
    if "review_recommendations" not in st.session_state:
        with st.spinner("🤖 Generating checklist recommendations..."):
            st.session_state.review_recommendations = engine.get_recommended_checklist_items(findings, code, lang)
        # Track which items have been added
        st.session_state.rec_added = set()

    recommendations = st.session_state.get("review_recommendations", [])

    if not recommendations:
        st.success("✅ No new checklist items recommended — your checklist looks comprehensive!")
        return

    st.markdown(f"**{len(recommendations)} item{'s' if len(recommendations) > 1 else ''} suggested** — select the ones you'd like to add to your checklist:")
    st.markdown("<br>", unsafe_allow_html=True)

    added_set = st.session_state.get("rec_added", set())
    selected_indices = []

    for i, item in enumerate(recommendations):
        already_added = i in added_set
        col_check, col_content = st.columns([0.5, 9.5])
        with col_check:
            # Vertically nudge the checkbox to align with the card
            st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
            checked = st.checkbox("", key=f"rec_check_{i}", value=False, disabled=already_added)
            if checked:
                selected_indices.append(i)
        with col_content:
            category = item.get('category', 'General')
            description = item.get('description', '')
            rationale = item.get('rationale', '')
            added_label = " &nbsp;✅ *Added*" if already_added else ""
            with st.container(border=True):
                # Category badge + added indicator on same line
                st.markdown(
                    f'<span style="background:rgba(99,179,237,0.18);color:#63b3ed;border-radius:12px;'
                    f'padding:2px 12px;font-size:0.78rem;font-weight:600;">🏷️ {html.escape(category)}</span>'
                    f'<span style="font-size:0.82rem;color:#68d391;margin-left:12px;">{added_label}</span>',
                    unsafe_allow_html=True
                )
                st.markdown(f"**{description}**")
                st.caption(f"💡 {rationale}")

    st.markdown("<br>", unsafe_allow_html=True)

    # Action buttons
    col_add, col_regen, _ = st.columns([2, 2, 6])
    with col_add:
        add_disabled = len(selected_indices) == 0
        if st.button(
            f"＋ Add {len(selected_indices)} Selected" if selected_indices else "＋ Add Selected",
            type="primary",
            disabled=add_disabled,
            key="add_rec_btn"
        ):
            try:
                conn = sqlite3.connect("checklist.db")
                cursor = conn.cursor()
                added_count = 0
                for idx in selected_indices:
                    if idx not in added_set:
                        item = recommendations[idx]
                        cursor.execute(
                            "INSERT INTO checklist (Category, Description) VALUES (?, ?)",
                            (item.get("category", "General"), item.get("description", ""))
                        )
                        added_set.add(idx)
                        added_count += 1
                conn.commit()
                conn.close()
                st.session_state.rec_added = added_set
                st.toast(f"✅ {added_count} item{'s' if added_count > 1 else ''} added to checklist!", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to add items: {e}")

    with col_regen:
        if st.button("🔄 Refresh", key="regen_rec_btn", help="Re-generate recommendations from AI"):
            st.session_state.pop("review_recommendations", None)
            st.session_state.pop("rec_added", None)
            st.rerun()

    # Show completion state
    if len(added_set) == len(recommendations):
        st.success("🎉 All recommendations have been added to your checklist!")


def render_report_page(engine):
    # Back button
    col1, col2 = st.columns([1, 10])
    with col1:
        if st.button("← Back"):
            st.session_state.page = "input"
            st.session_state.start_review = False
            # Clear post-review state when going back
            for key in ["review_summary", "review_recommendations", "rec_added"]:
                st.session_state.pop(key, None)
            st.rerun()

    st.divider()
    st.subheader("Review Report")

    # Placeholder for streaming status
    status_placeholder = st.empty()
    # Placeholder for the summary card (shown above tabs)
    summary_placeholder = st.empty()

    # Three tabs: Table View | Code View | Recommended Checklist
    tab1, tab2, tab3 = st.tabs(["📊 Table View", "💻 Code View", "💡 Recommended Checklist"])

    with tab1:
        results_placeholder = st.empty()

    with tab2:
        code_view = st.empty()
        code_view.info("Awaiting review completion...")

    # ── NEW REVIEW FLOW ──────────────────────────────────────────────────────
    if st.session_state.get("start_review", False):
        st.session_state.start_review = False
        # Clear any stale post-review data from a previous run
        for key in ["review_summary", "review_recommendations", "rec_added"]:
            st.session_state.pop(key, None)

        st.session_state.review_results = []
        st.session_state.review_findings = []
        status_placeholder.info("Running Analysis...")

        code = st.session_state.get("review_code", "")
        lang = st.session_state.get("review_language", "python")
        cat = st.session_state.get("review_category", None)

        try:
            for result in engine.analyze_stream(code, filter_category=cat, language=lang):
                st.session_state.review_findings.append(result)
                review_comment = result['comment']
                line_info = f"(Line: {result['line_number']})" if result['line_number'] != "General" else ""
                full_review = f"{review_comment} {line_info}"

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

                df = pd.DataFrame(st.session_state.review_results)
                df = df[["Checklist Item", "Review", "Confidence", "Status"]]
                results_placeholder.dataframe(df, use_container_width=True, hide_index=True)

            status_placeholder.success("✅ Review Complete!")

            # Render code view
            with tab2:
                code_view.markdown(
                    generate_highlighted_code(code, st.session_state.review_findings, language=lang),
                    unsafe_allow_html=True
                )

            # Generate & display summary ABOVE the tabs
            with status_placeholder:
                pass  # keep "Review Complete!" visible
            summary_text = engine.get_review_summary(st.session_state.review_findings, code, lang)
            st.session_state.review_summary = summary_text
            with summary_placeholder.container():
                _render_summary_card(summary_text, st.session_state.review_findings)

        except Exception as e:
            status_placeholder.error(f"Error during review: {str(e)}")

    # ── REVISIT / RELOAD FLOW ────────────────────────────────────────────────
    else:
        if st.session_state.get("review_results"):
            with tab1:
                df = pd.DataFrame(st.session_state.review_results)
                cols = ["Checklist Item", "Review", "Confidence", "Status"]
                if all(col in df.columns for col in cols):
                    df = df[cols]
                results_placeholder.dataframe(df, use_container_width=True, hide_index=True)

            with tab2:
                if "review_findings" in st.session_state and "review_code" in st.session_state:
                    lang_saved = st.session_state.get("review_language", "python")
                    code_view.markdown(
                        generate_highlighted_code(
                            st.session_state.review_code,
                            st.session_state.review_findings,
                            language=lang_saved
                        ),
                        unsafe_allow_html=True
                    )
                else:
                    code_view.info("Code view not available.")

            # Show summary if already generated
            if st.session_state.get("review_summary"):
                with summary_placeholder.container():
                    _render_summary_card(
                        st.session_state.review_summary,
                        st.session_state.get("review_findings", [])
                    )
        else:
            status_placeholder.info("No active review. Go back and submit code.")

    # ── RECOMMENDATIONS TAB (always rendered, loads lazily) ──────────────────
    with tab3:
        if st.session_state.get("review_results"):
            _render_recommendations_tab(engine)
        else:
            st.info("Complete a review to see AI-recommended checklist items.")


def render_input_page(engine, focus_cdl):
    st.subheader("Input Code")
    
    with st.expander("Manage Checklists", expanded=False):
        try:
            conn = sqlite3.connect("checklist.db")
            # Read existing data
            df_checklist = pd.read_sql_query("SELECT * FROM checklist", conn)
            
            # Extract unique categories for dropdown
            existing_categories = df_checklist["Category"].dropna().unique().tolist()
            
            # Initialize a dynamic key for the editor to allow hard resets
            if "editor_key" not in st.session_state:
                st.session_state.editor_key = 0

            current_key = f"checklist_editor_{st.session_state.editor_key}"

            # Show interactive data editor
            st.markdown("Edit the checklist directly below. You can add new rows at the bottom.")
            st.info("💡 **Tip for Deleting Rows**: Click the empty cell on the far left of a row to select it, then press the **Delete** key on your keyboard.")
            
            edited_df = st.data_editor(
                df_checklist,
                use_container_width=True,
                num_rows="dynamic",
                hide_index=True,
                column_config={
                    "id": None, # Hides the ID column securely
                    "Category": st.column_config.SelectboxColumn(
                        "Category",
                        help="Select an existing category, or type to add a new one if permitted by Streamlit",
                        width="medium",
                        options=existing_categories,
                        required=True,
                    ),
                    "Description": st.column_config.TextColumn("Description", width="large", required=True)
                },
                key=current_key
            )
            
            # Check if there are any pending changes
            has_changes = False
            if current_key in st.session_state:
                editor_state = st.session_state[current_key]
                if editor_state.get("edited_rows") or editor_state.get("added_rows") or editor_state.get("deleted_rows"):
                    has_changes = True

            # Layout for buttons (always visible)
            st.markdown("<br>", unsafe_allow_html=True) # Add a tiny space below table
            col1, col2, _ = st.columns([1.5, 1.5, 7]) # Tight columns so buttons don't stretch
            
            with col1:
                # Disabled if no changes
                if st.button("Save Changes", type="primary", disabled=not has_changes):
                    cursor = conn.cursor()
                    cursor.execute('DROP TABLE IF EXISTS checklist')
                    cursor.execute('''
                        CREATE TABLE checklist (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            Category TEXT,
                            Description TEXT
                        )
                    ''')
                    
                    if 'id' in edited_df.columns:
                        edited_df = edited_df.drop('id', axis=1)
                    
                    edited_df.to_sql('checklist', conn, if_exists='append', index=False)
                    conn.commit()
                    st.success("✅ Changes saved successfully! Reloading...")
                    time.sleep(1.5)
                    
                    # Force a complete remount of the data editor
                    st.session_state.editor_key += 1
                    st.rerun()
                    
            with col2:
                # Disabled if no changes
                if st.button("Revert", disabled=not has_changes):
                    # Force a complete remount of the data editor to wipe unsaved UI state
                    st.session_state.editor_key += 1
                    st.rerun()
                
            conn.close()
        except Exception as e:
            st.error(f"Could not load checklist from DB: {e}")

    input_method = st.radio("Select Input Method:", ("Paste Code", "Upload File", "GitHub PR"), horizontal=True, key="input_method_radio")
    code_content = ""
    language = "python" # default

    if input_method == "Paste Code":
        language = st.selectbox("Select Language", ["python", "sql", "hql", "jil"])
        
        # Show info if in Sandbox Mode
        if st.session_state.get("sandbox_mode", False):
            st.info("Sandbox Mode: Loaded sample file 'CIN_XML_parsing - input file.py'")
        
        code_content = st.text_area(f"Paste your {language} code here:", height=300, key="input_code_area")
    elif input_method == "Upload File":
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
    elif input_method == "GitHub PR":
        render_github_pr_flow(focus_cdl)
        return  # GitHub flow handles its own "Run Review" button

    # Operations (for Paste Code / Upload File)
    if code_content.strip():
        if st.button("Run Review", type="primary"):
            st.session_state.review_code = code_content
            st.session_state.review_language = language
            st.session_state.review_category = "Code CDL Standards" if focus_cdl else None
            st.session_state.start_review = True
            st.session_state.page = "report"
            st.rerun()


def render_github_pr_flow(focus_cdl):
    """Multi-step GitHub PR selection and review flow."""
    gh_container = st.container()
    with gh_container:
        st.markdown("---")
        st.markdown("#### 🔗 Connect to GitHub")
        
        # --- Step 1: Connection ---
        col1, col2 = st.columns(2)
        with col1:
            gh_username = st.text_input(
                "GitHub Username",
                value=os.getenv("GITHUB_USERNAME", ""),
                key="gh_username_input"
            )
        with col2:
            gh_pat = st.text_input(
                "Personal Access Token (PAT)",
                value=os.getenv("GITHUB_PAT", ""),
                type="password",
                key="gh_pat_input"
            )
        
        if not gh_username or not gh_pat:
            st.info("Enter your GitHub username and PAT to connect.")
            return
        
        connect_btn = st.button("🔌 Connect", key="gh_connect_btn")
        
        if connect_btn:
            try:
                client = GitHubClient(token=gh_pat, username=gh_username)
                user_info = client.validate_connection()
                st.session_state.gh_client = client
                st.session_state.gh_owner = gh_username
                st.session_state.gh_connected = True
                st.session_state.gh_user_info = user_info
                # Clear downstream selections on reconnect
                for key in ["gh_repos", "gh_prs", "gh_pr_files", "gh_selected_repo", "gh_selected_pr"]:
                    st.session_state.pop(key, None)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")
                st.session_state.gh_connected = False
                return
        
        if not st.session_state.get("gh_connected", False):
            return
        
        # Show connected status
        user_info = st.session_state.get("gh_user_info", {})
        st.success(f"✅ Connected as **{user_info.get('name', gh_username)}** (@{user_info.get('login', gh_username)})")
        
        client: GitHubClient = st.session_state.gh_client
        owner = st.session_state.gh_owner
        
        # --- Step 2: Select Repository ---
        st.markdown("---")
        st.markdown("#### 📁 Select Repository")
        
        # Fetch repos if not cached
        if "gh_repos" not in st.session_state:
            try:
                st.session_state.gh_repos = client.list_repos(owner)
            except Exception as e:
                st.error(f"Failed to fetch repos: {e}")
                return
        
        repos = st.session_state.gh_repos
        if not repos:
            st.warning("No repositories found for this user.")
            return
        
        repo_names = [r["name"] for r in repos]
        selected_repo = st.selectbox(
            "Repository",
            options=repo_names,
            key="gh_repo_select",
            format_func=lambda name: f"{name} ({next((r['language'] for r in repos if r['name'] == name), 'Unknown')})"
        )
        
        if not selected_repo:
            return
        
        # Clear PR cache if repo changed
        if st.session_state.get("gh_selected_repo") != selected_repo:
            st.session_state.gh_selected_repo = selected_repo
            for key in ["gh_prs", "gh_pr_files", "gh_selected_pr"]:
                st.session_state.pop(key, None)
        
        # --- Step 3: Browse Pull Requests ---
        st.markdown("---")
        st.markdown("#### 🔀 Open Pull Requests")
        
        # Fetch PRs if not cached
        if "gh_prs" not in st.session_state:
            try:
                with st.spinner("Fetching pull requests..."):
                    st.session_state.gh_prs = client.list_pull_requests(owner, selected_repo)
            except Exception as e:
                st.error(f"Failed to fetch PRs: {e}")
                return
        
        prs = st.session_state.gh_prs
        if not prs:
            st.info("No open pull requests found in this repository.")
            return
        
        # Show PRs in a styled table
        pr_display = pd.DataFrame([
            {
                "#": pr["number"],
                "Title": pr["title"],
                "Author": pr["author"],
                "Date": pr["created_at"],
                "Branch": f"{pr['head_branch']} → {pr['base_branch']}",
            }
            for pr in prs
        ])
        st.dataframe(pr_display, use_container_width=True, hide_index=True)
        
        # PR selection
        pr_options = {f"PR #{pr['number']}: {pr['title']}": pr["number"] for pr in prs}
        selected_pr_label = st.selectbox("Select a PR to review", options=list(pr_options.keys()), key="gh_pr_select")
        selected_pr_num = pr_options[selected_pr_label]
        
        # Clear files cache if PR changed
        if st.session_state.get("gh_selected_pr") != selected_pr_num:
            st.session_state.gh_selected_pr = selected_pr_num
            st.session_state.pop("gh_pr_files", None)
        
        # --- Step 4: Show Changed Files ---
        st.markdown("---")
        st.markdown("#### 📄 Changed Files")
        
        if "gh_pr_files" not in st.session_state:
            try:
                with st.spinner("Fetching changed files..."):
                    st.session_state.gh_pr_files = client.get_pr_files(owner, selected_repo, selected_pr_num)
            except Exception as e:
                st.error(f"Failed to fetch PR files: {e}")
                return
        
        pr_files = st.session_state.gh_pr_files
        if not pr_files:
            st.info("No files changed in this PR.")
            return
        
        # Show file list with status
        status_icons = {
            "added": "🟢 Added",
            "modified": "🟡 Modified",
            "removed": "🔴 Removed",
            "renamed": "🔵 Renamed",
        }
        
        files_df = pd.DataFrame([
            {
                "File": f["filename"],
                "Status": status_icons.get(f["status"], f["status"]),
                "Changes": f"+{f['additions']} / -{f['deletions']}",
                "Language": f["language"],
                "Reviewable": "✅" if f["is_reviewable"] else "⛔",
            }
            for f in pr_files
        ])
        st.dataframe(files_df, use_container_width=True, hide_index=True)
        
        # File selection — only reviewable files
        reviewable_files = [f for f in pr_files if f["is_reviewable"]]
        if not reviewable_files:
            st.warning("No reviewable code files in this PR (only binary or deleted files).")
            return
        
        selected_file = st.selectbox(
            "Select a file to review",
            options=[f["filename"] for f in reviewable_files],
            key="gh_file_select"
        )
        
        # --- Step 5: Run Review ---
        if st.button("🚀 Run Review", type="primary", key="gh_run_review"):
            # Get the PR detail to find the head branch
            selected_pr_info = next((pr for pr in prs if pr["number"] == selected_pr_num), None)
            head_branch = selected_pr_info["head_branch"] if selected_pr_info else "main"
            
            # Get the file metadata
            file_meta = next((f for f in reviewable_files if f["filename"] == selected_file), None)
            
            file_content = None
            try:
                with st.spinner(f"Fetching `{selected_file}` from branch `{head_branch}`..."):
                    file_content = client.get_file_content(owner, selected_repo, selected_file, ref=head_branch)
            except Exception as e:
                st.error(f"Failed to fetch file content: {e}")
                
            if file_content:
                # Set session state for the review engine
                st.session_state.review_code = file_content
                st.session_state.review_language = file_meta["language"] if file_meta else "python"
                st.session_state.review_category = "Code CDL Standards" if focus_cdl else None
                st.session_state.start_review = True
                st.session_state.page = "report"
                st.session_state.gh_review_context = {
                    "repo": f"{owner}/{selected_repo}",
                    "pr": f"PR #{selected_pr_num}",
                    "file": selected_file,
                    "branch": head_branch,
                }
                # Rerun immediately to clear the input page and show the report page
                st.rerun()

def main():
    if "page" not in st.session_state:
        st.session_state.page = "input"
    
    # Ensure session state variables exist
    if "review_results" not in st.session_state:
        st.session_state.review_results = []
    if "review_findings" not in st.session_state:
        st.session_state.review_findings = []
    if "gh_connected" not in st.session_state:
        st.session_state.gh_connected = False

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
        st.subheader("Sandbox")
        
        def on_sandbox_toggle():
            if st.session_state.sandbox_cb:
                st.session_state.sandbox_mode = True
                st.session_state.input_method_radio = "Paste Code"
                try:
                    sample_path = "CIN_XML_parsing - input file.py"
                    if os.path.exists(sample_path):
                        with open(sample_path, "r", encoding='utf-8') as f:
                            st.session_state.input_code_area = f.read()
                except Exception:
                    pass
            else:
                st.session_state.sandbox_mode = False
                st.session_state.input_code_area = ""
                
        if "sandbox_cb" not in st.session_state:
            st.session_state.sandbox_cb = st.session_state.get("sandbox_mode", False)
            
        st.checkbox("Sandbox Mode (Offline Demo)", key="sandbox_cb", on_change=on_sandbox_toggle, help="Use mock data to test the UI without LLM keys.")
        sandbox_mode = st.session_state.get("sandbox_cb", False)

    # Initialize Engine (No API Key needed from UI)
    engine = ReviewEngine("checklist.db", ai_provider=ai_provider, ai_model=model_name, sandbox_mode=sandbox_mode)

    # Main content area with clear page separation
    if st.session_state.page == "input":
        render_input_page(engine, focus_cdl)
    elif st.session_state.page == "report":
        render_report_page(engine)

if __name__ == "__main__":
    main()

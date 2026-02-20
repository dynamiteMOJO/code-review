
import re
import ast
import sqlite3
import pandas as pd
from typing import List, Dict, Any
import os
import json

# Import the new chat wrapper
from iliad_client import IliadChatClient

class AIReviewer:
    def __init__(self, provider: str = 'openai', model_name: str = 'gpt-4'):
        self.chat_client = None
        self.is_configured = False
        
        try:
            # Initialize the custom Iliad Chat wrapper
            self.chat_client = IliadChatClient(model_provider=provider, model_name=model_name)
            self.is_configured = True
        except Exception as e:
            print(f"Error initializing Iliad Chat: {e}")

    def review_item(self, code_snippet: str, checklist_item: str, language: str = "python") -> Dict[str, Any]:
        if not self.is_configured:
            return {
                "checklist_item": checklist_item,
                "confidence": "0%",
                "comment": "AI Client Env Config Missing",
                "status": "Unsure",
                "line_number": "General"
            }

        # Prepend line numbers to the code snippet for the AI
        lines = code_snippet.splitlines()
        numbered_code = "\n".join([f"{i+1}: {line}" for i, line in enumerate(lines)])

        system_prompt = f"You are a Senior Data Engineer Reviewer. Analyze the {language} code against the specific rule. The code has line numbers at the beginning of each line (e.g., '1: code'). Use these numbers to identify the 'line_number' in your response."
        user_prompt = f"""
        Rule: "{checklist_item}"
        
        Code:
        ```{language}
        {numbered_code}
        ```
        
        Analyze the code against the rule.
        Return ONLY a JSON object with the following keys:
        - "status": "Pass", "Fail", or "Unsure"
        - "confidence": A percentage score (e.g., "95%").
        - "comment": The actual review comment. If there is a violation, explain why. Short & concise.
        - "line_number": The exact line number(s) where the issue occurs (e.g., "10", "15-20"). If not applicable/general, use "General".
        - "substring": The exact substring from the code line that causes the issue. It MUST match the code character-for-character so it can be highlighted. If the same word appears multiple times on the line, provide a longer substring to make it unique (e.g., 'obj.property' instead of just 'property').
        
        Ensure the output is valid JSON. Do not include any markdown formatting like ```json ... ```.
        """
        
        try:
            # Use generate() method from SimplifiedIliadChat
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            content = self.chat_client.generate(messages)

            # Attempt to clean markdown json blocks if present
            clean_content = content.replace("```json", "").replace("```", "").strip()
            
            try:
                data = json.loads(clean_content)
                return {
                    "checklist_item": checklist_item,
                    "confidence": data.get("confidence", "N/A"),
                    "comment": data.get("comment", "No comment provided"),
                    "status": data.get("status", "Unsure"),
                    "line_number": str(data.get("line_number", "General")),
                    "substring": data.get("substring", "")
                }
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return {
                    "checklist_item": checklist_item,
                    "confidence": "Low",
                    "comment": f"Raw AI Response: {content}",
                    "status": "Unsure",
                    "line_number": "General"
                }

        except Exception as e:
            return {
                "checklist_item": checklist_item,
                "confidence": "0%",
                "comment": f"Error: {str(e)}",
                "status": "Error",
                "line_number": "General"
            }

    def generate_review_summary(self, findings: list, code: str, language: str = "python") -> str:
        """Generate a crisp, actionable review summary from all findings."""
        if not self.is_configured:
            return "_AI Client not configured — summary unavailable._"
        
        # Compact findings into a text block for the prompt
        findings_text = "\n".join([
            f"- [{f.get('status','?')}] {f.get('checklist_item','')}: {f.get('comment','')} (Line: {f.get('line_number','General')})"
            for f in findings
        ])
        
        system_prompt = "You are a senior code reviewer. Produce a concise, actionable code review summary."
        user_prompt = f"""
        Language: {language}
        
        Review findings:
        {findings_text}
        
        Write a structured Markdown summary with exactly these sections:
        ## Overall Verdict
        One sentence verdict (e.g. "❌ Code has critical issues that must be fixed before merge.").
        
        ## Critical Issues
        Bullet list of Fail-status items with specific action needed. Be concise.
        
        ## Warnings
        Bullet list of Warning/Unsure items. Be concise. Skip if none.
        
        ## Top Action Items
        Numbered list of the 3–5 most important concrete actions the developer must take.
        
        Keep the entire summary under 300 words. Be direct, no fluff.
        Return only the Markdown text, no code fences.
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            return self.chat_client.generate(messages).strip()
        except Exception as e:
            return f"_Error generating summary: {e}_"

    def recommend_checklist_items(self, findings: list, code: str, language: str, existing_items: list) -> list:
        """Recommend up to 5 new checklist items not already covered."""
        if not self.is_configured:
            return []
        
        existing_text = "\n".join([f"- {item}" for item in existing_items])
        findings_text = "\n".join([
            f"- [{f.get('status','?')}] {f.get('checklist_item','')}: {f.get('comment','')}"
            for f in findings
        ])
        
        system_prompt = "You are an expert code quality analyst. Recommend new checklist items based on code review findings."
        user_prompt = f"""
        Language: {language}
        
        Existing checklist items (do NOT suggest these again):
        {existing_text}
        
        Review findings from this code:
        {findings_text}
        
        Suggest up to 5 NEW, important checklist items that are NOT already covered by the existing list.
        Focus only on high-value items relevant to {language} data engineering code quality.
        
        Return ONLY a JSON array. Each element must have these keys:
        - "category": Short category name (e.g. "Error Handling", "Performance", "Security")
        - "description": The checklist item description. Concise, actionable, testable.
        - "rationale": One sentence explaining why this item is important based on what was seen.
        
        If no new items are needed, return an empty array [].
        Do not include any markdown formatting like ```json.
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            content = self.chat_client.generate(messages)
            clean = content.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean)
            return result if isinstance(result, list) else []
        except Exception as e:
            return []


class ReviewEngine:
    def __init__(self, checklist_path: str = "checklist.db", ai_provider: str = "openai", ai_model: str = "gpt-4", sandbox_mode: bool = False):
        self.checklist_path = checklist_path
        self.checklist = self._load_checklist()
        self.sandbox_mode = sandbox_mode
        self.sandbox_data = []
        if self.sandbox_mode:
            self._load_sandbox_data()
        
        # Only init AI if NOT in sandbox mode (or you could always init it, but save resources if sandbox)
        if not self.sandbox_mode:
            self.ai_reviewer = AIReviewer(provider=ai_provider, model_name=ai_model)
        else:
            self.ai_reviewer = None

    def _load_checklist(self) -> pd.DataFrame:
        try:
            if self.checklist_path.endswith('.csv'):
                return pd.read_csv(self.checklist_path)
            
            # Use SQLite
            conn = sqlite3.connect(self.checklist_path)
            df = pd.read_sql_query("SELECT Category, Description FROM checklist", conn)
            conn.close()
            return df
        except Exception as e:
            print(f"Error loading checklist from {self.checklist_path}: {e}")
            return pd.DataFrame(columns=["Category", "Description"])

    def _load_sandbox_data(self):
        try:
            with open("sandbox_data.json", "r") as f:
                self.sandbox_data = json.load(f)
        except Exception as e:
            print(f"Error loading sandbox data: {e}")
            self.sandbox_data = []

    def analyze_stream(self, code_content: str, filter_category: str = "Code CDL Standards", language: str = "python"):
        """
        Yields review results one by one using LLM or Sandbox Data.
        """
        
        # 1. Syntax Check (Basic validation) - Run even in sandbox for realism, or skip if strictly mocking
        if language == "python":
            try:
                ast.parse(code_content)
            except SyntaxError as e:
                yield {
                    "checklist_item": "Syntax Check",
                    "confidence": "100%",
                    "comment": f"Syntax Error: {e.msg}",
                    "status": "Fail",
                    "line_number": str(e.lineno)
                }
                return

        # SANDBOX PATH
        if self.sandbox_mode:
            import time
            import random
            
            # Simulate "thinking" time
            time.sleep(0.2)
            
            for finding in self.sandbox_data:
                # Simulate streaming delay between items
                time.sleep(random.uniform(0.1, 0.3))
                yield finding
            return

        # REAL AI PATH
        # 2. Filter Checklist
        valid_items = self.checklist
        if filter_category:
            valid_items = self.checklist[self.checklist['Category'] == filter_category]
        
        # 3. Process all items via AI
        for _, row in valid_items.iterrows():
            desc = row['Description']
            yield self.ai_reviewer.review_item(code_content, desc, language=language)

    def get_review_summary(self, findings: list, code: str, language: str = "python") -> str:
        """Return an AI-generated review summary. Returns mock in sandbox mode."""
        if self.sandbox_mode:
            fail_count = sum(1 for f in findings if f.get('status') == 'Fail')
            warn_count = sum(1 for f in findings if f.get('status') == 'Warning')
            verdict = "❌ Code has critical issues that must be fixed." if fail_count > 0 else "⚠️ Code has warnings that should be addressed."
            return f"""## Overall Verdict
{verdict}

## Critical Issues
{'- No critical issues found.' if fail_count == 0 else chr(10).join([f'- **{f["checklist_item"]}**: {f["comment"]}' for f in findings if f.get('status') == 'Fail'][:5])}

## Warnings
{'- No warnings.' if warn_count == 0 else chr(10).join([f'- **{f["checklist_item"]}**: {f["comment"]}' for f in findings if f.get('status') == 'Warning'][:3])}

## Top Action Items
1. Fix all critical issues before merging.
2. Review all warning-level findings and assess risk.
3. Ensure error handling is consistent throughout the code.
"""
        return self.ai_reviewer.generate_review_summary(findings, code, language)

    def get_recommended_checklist_items(self, findings: list, code: str, language: str = "python") -> list:
        """Return AI-recommended new checklist items. Returns mock in sandbox mode."""
        if self.sandbox_mode:
            return [
                {
                    "category": "Error Handling",
                    "description": "All file I/O operations must be wrapped in try-except blocks with specific exception types.",
                    "rationale": "Generic bare except clauses were observed which can mask unexpected errors."
                },
                {
                    "category": "Logging",
                    "description": "Use structured logging with log levels (DEBUG/INFO/WARNING/ERROR) instead of print statements.",
                    "rationale": "Multiple print() calls were found that won't appear in production log aggregation systems."
                },
                {
                    "category": "Code Documentation",
                    "description": "All functions with more than 3 parameters must include a docstring explaining purpose, args, and return value.",
                    "rationale": "Several multi-parameter functions lacked docstrings, reducing maintainability."
                }
            ]
        # Load existing checklist items for de-duplication
        existing_items = self.checklist['Description'].tolist() if not self.checklist.empty else []
        return self.ai_reviewer.recommend_checklist_items(findings, code, language, existing_items)



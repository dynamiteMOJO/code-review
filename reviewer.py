
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



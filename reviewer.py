
import re
import ast
import pandas as pd
from typing import List, Dict, Any
import os

# Optional imports for AI
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

class ASTAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.findings = []
        self.has_try_except = False

    def visit_Call(self, node):
        # Check for print()
        if isinstance(node.func, ast.Name) and node.func.id == "print":
             self.findings.append({
                "check": "No 'print' statements (Use Logger)",
                "status": "Warning",
                "line": node.lineno,
                "message": f"Found print statement on line {node.lineno}. Use a logger instead.",
                "category": "Code CDL Standards"
            })
        
        # Check for .toPandas()
        if isinstance(node.func, ast.Attribute) and node.func.attr == "toPandas":
             self.findings.append({
                "check": "Avoid .toPandas() on huge datasets",
                "status": "Warning",
                "line": node.lineno,
                "message": f"Found .toPandas() on line {node.lineno}. This can cause OOM errors on large datasets.",
                "category": "Optimization Checks"
            })
            
        # Check for sys.exit(1) or exit(1) in generic calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "exit":
             # This matches things like sys.exit
             self.findings.append({
                "check": "Proper exit codes used",
                "status": "Info",
                "line": node.lineno,
                "message": f"Found exit call on line {node.lineno}. Verification needed context.",
                 "category": "Code CDL Standards"
            })
        elif isinstance(node.func, ast.Name) and node.func.id == "exit":
             self.findings.append({
                "check": "Proper exit codes used",
                "status": "Info",
                "line": node.lineno,
                "message": f"Found exit call on line {node.lineno}. Verification needed context.",
                 "category": "Code CDL Standards"
            })

        self.generic_visit(node)

    def visit_Try(self, node):
        self.has_try_except = True
        self.generic_visit(node)
        
    def visit_Assign(self, node):
        # Primitive secret detection in variable names
        for target in node.targets:
            if isinstance(target, ast.Name):
                if re.search(r'(password|secret|key|token)', target.id, re.IGNORECASE):
                     self.findings.append({
                        "check": "No plain text passwords/secrets",
                        "status": "Fail",
                        "line": node.lineno,
                        "message": f"Potential hardcoded secret variable '{target.id}' on line {node.lineno}.",
                        "category": "Security Checks"
                    })
        self.generic_visit(node)


class AIReviewer:
    def __init__(self, provider: str, api_key: str):
        self.provider = provider
        self.api_key = api_key
        self.client = None
        self.is_configured = False

        if not api_key:
            return

        if provider == "OpenAI" and OpenAI:
            try:
                self.client = OpenAI(api_key=api_key)
                self.is_configured = True
            except Exception as e:
                print(f"Error initializing OpenAI client: {e}")
        
        elif provider == "Gemini" and genai:
            try:
                genai.configure(api_key=api_key)
                self.client = genai.GenerativeModel('models/gemini-2.5-flash')
                self.is_configured = True
            except Exception as e:
                print(f"Error initializing Gemini client: {e}")

    def review_item(self, code_snippet: str, checklist_item: str) -> Dict[str, Any]:
        if not self.is_configured:
            return {"status": "Manual Review", "reason": "AI not configured"}

        prompt = f"""
        You are a Senior Data Engineer Reviewer.
        Analyze this Python/PySpark code snippet against the following rule:
        Rule: "{checklist_item}"
        
        Code:
        ```python
        {code_snippet}
        ```
        
        Return ONLY a JSON-like text with:
        - "status": "Pass" or "Fail" or "Unsure"
        - "reason": A brief explanation (max 1 sentence).
        """
        
        try:
            content = ""
            if self.provider == "OpenAI":
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150
                )
                content = response.choices[0].message.content
            
            elif self.provider == "Gemini":
                response = self.client.generate_content(prompt)
                content = response.text

            # Heuristic Parsing
            if "Pass" in content:
                return {"status": "Pass", "reason": content}
            elif "Fail" in content:
                 return {"status": "Fail", "reason": content}
            else:
                 return {"status": "Unsure", "reason": content}

        except Exception as e:
            return {"status": "Error", "reason": str(e)}


class ReviewEngine:
    def __init__(self, checklist_path: str = "checklist.csv", ai_provider: str = "OpenAI", ai_api_key: str = None):
        self.checklist_path = checklist_path
        self.checklist = self._load_checklist()
        self.ai_reviewer = AIReviewer(ai_provider, ai_api_key)

    def _load_checklist(self) -> pd.DataFrame:
        try:
            return pd.read_csv(self.checklist_path)
        except Exception as e:
            print(f"Error loading checklist: {e}")
            return pd.DataFrame(columns=["Category", "Description"])

    def analyze(self, code_content: str, filter_category: str = "Code CDL Standards") -> Dict[str, Any]:
        results = {
            "automated_results": [],
            "ai_results": [],
            "manual_checklist": [],
            "summary": {"passed": 0, "warnings": 0, "failed": 0}
        }

        # 1. Static Analysis (AST)
        try:
            tree = ast.parse(code_content)
            analyzer = ASTAnalyzer()
            analyzer.visit(tree)
            results["automated_results"].extend(analyzer.findings)
            
             # File-wide AST checks
            if not analyzer.has_try_except:
                 results["automated_results"].append({
                    "check": "Try-Catch blocks present",
                    "status": "Warning",
                    "line": 0,
                    "message": "No 'try-except' blocks found. Ensure business logic is handled safely.",
                    "category": "Code CDL Standards"
                })

        except SyntaxError as e:
            results["automated_results"].append({
                "check": "Syntax Check",
                "status": "Fail",
                "line": e.lineno,
                "message": f"Syntax Error: {e.msg}",
                "category": "General"
            })
            return results

        # 2. Filter Checklist
        valid_items = self.checklist
        if filter_category:
            valid_items = self.checklist[self.checklist['Category'] == filter_category]
        
        # 3. Process remaining items (AI vs Manual)
        # Identify checks already covered by Static Analysis to avoid duplication
        covered_concepts = ["print", "toPandas", "exit", "try catch", "password", "secret"]
        
        for _, row in valid_items.iterrows():
            desc = row['Description']
            category = row['Category']
            
            # customizable exclusion logic
            is_covered = any(c.lower() in desc.lower() for c in covered_concepts)
            
            if not is_covered:
                # Send to AI
                ai_res = self.ai_reviewer.review_item(code_content, desc)
                if ai_res["status"] in ["Pass", "Fail"]:
                    results["ai_results"].append({
                        "check": desc,
                        "status": ai_res["status"],
                        "message": ai_res["reason"],
                        "category": category
                    })
                else:
                    # Fallback to Manual
                    results["manual_checklist"].append({
                         "Category": category,
                         "Description": desc,
                         "AI_Note": ai_res.get("reason", "")
                    })

        return results

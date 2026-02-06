
import re
import ast
import pandas as pd
from typing import List, Dict, Any
import os

# Import the new chat wrapper
from iliad_client import IliadChatClient

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
    def __init__(self, provider: str = 'openai', model_name: str = 'gpt-4'):
        self.chat_client = None
        self.is_configured = False
        
        try:
            # Initialize the custom Iliad Chat wrapper
            self.chat_client = IliadChatClient(model_provider=provider, model_name=model_name)
            self.is_configured = True
        except Exception as e:
            print(f"Error initializing Iliad Chat: {e}")

    def review_item(self, code_snippet: str, checklist_item: str) -> Dict[str, Any]:
        if not self.is_configured:
            return {"status": "Manual Review", "reason": "AI Client Env Config Missing"}

        system_prompt = "You are a Senior Data Engineer Reviewer. Analyze the code against the specific rule."
        user_prompt = f"""
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
            # Use generate() method from SimplifiedIliadChat
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            content = self.chat_client.generate(messages)

            if "Pass" in content:
                return {"status": "Pass", "reason": content}
            elif "Fail" in content:
                 return {"status": "Fail", "reason": content}
            else:
                 return {"status": "Unsure", "reason": content}

        except Exception as e:
            return {"status": "Error", "reason": str(e)}


class ReviewEngine:
    def __init__(self, checklist_path: str = "checklist.csv", ai_provider: str = "openai", ai_model: str = "gpt-4"):
        self.checklist_path = checklist_path
        self.checklist = self._load_checklist()
        # Pass provider/model to AIReviewer, credentials are handled via ENV
        self.ai_reviewer = AIReviewer(provider=ai_provider, model_name=ai_model)

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
        
        # 3. Process remaining items
        covered_concepts = ["print", "toPandas", "exit", "try catch", "password", "secret"]
        
        for _, row in valid_items.iterrows():
            desc = row['Description']
            category = row['Category']
            is_covered = any(c.lower() in desc.lower() for c in covered_concepts)
            
            if not is_covered:
                ai_res = self.ai_reviewer.review_item(code_content, desc)
                if ai_res["status"] in ["Pass", "Fail"]:
                    results["ai_results"].append({
                        "check": desc,
                        "status": ai_res["status"],
                        "message": ai_res["reason"],
                        "category": category
                    })
                else:
                    results["manual_checklist"].append({
                         "Category": category,
                         "Description": desc,
                         "AI_Note": ai_res.get("reason", "")
                    })

        return results

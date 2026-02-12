import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv()


class GitHubClient:
    """Lightweight GitHub REST API wrapper for PR review workflows."""

    BASE_URL = "https://api.github.com"

    # Map file extensions to language identifiers
    EXTENSION_MAP = {
        ".py": "python",
        ".sql": "sql",
        ".hql": "hql",
        ".jil": "jil",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".scala": "scala",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".xml": "xml",
        ".csv": "csv",
        ".md": "markdown",
        ".txt": "text",
    }

    def __init__(self, token: str = None, username: str = None):
        """
        Initialize the GitHub client.

        Args:
            token: GitHub Personal Access Token. Falls back to GITHUB_PAT env var.
            username: GitHub username. Falls back to GITHUB_USERNAME env var.
        """
        self.token = token or os.getenv("GITHUB_PAT", "")
        self.username = username or os.getenv("GITHUB_USERNAME", "")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CodeReviewApp",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def _get(self, endpoint: str, params: dict = None) -> dict | list:
        """Make an authenticated GET request to the GitHub API."""
        url = f"{self.BASE_URL}{endpoint}"
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def validate_connection(self) -> dict:
        """
        Validate the PAT by fetching the authenticated user's info.

        Returns:
            dict with 'login', 'name', 'avatar_url'

        Raises:
            requests.HTTPError if authentication fails
        """
        data = self._get("/user")
        return {
            "login": data["login"],
            "name": data.get("name", data["login"]),
            "avatar_url": data.get("avatar_url", ""),
        }

    def list_repos(self, owner: str = None) -> list[dict]:
        """
        List repositories for a user.

        Args:
            owner: GitHub username. Defaults to self.username.

        Returns:
            List of dicts with 'name', 'full_name', 'description', 'language', 'private'
        """
        owner = owner or self.username
        repos = self._get(f"/users/{owner}/repos", params={"per_page": 100, "sort": "updated"})
        return [
            {
                "name": r["name"],
                "full_name": r["full_name"],
                "description": r.get("description") or "",
                "language": r.get("language") or "Unknown",
                "private": r["private"],
            }
            for r in repos
        ]

    def list_pull_requests(self, owner: str, repo: str, state: str = "open") -> list[dict]:
        """
        List pull requests for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            state: PR state filter ('open', 'closed', 'all')

        Returns:
            List of dicts with PR info
        """
        prs = self._get(f"/repos/{owner}/{repo}/pulls", params={"state": state, "per_page": 50})
        return [
            {
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["user"]["login"],
                "created_at": pr["created_at"][:10],  # Just the date
                "head_branch": pr["head"]["ref"],
                "base_branch": pr["base"]["ref"],
                "state": pr["state"],
                "html_url": pr["html_url"],
            }
            for pr in prs
        ]

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """
        Get the list of files changed in a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of dicts with file change info
        """
        files = self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}/files", params={"per_page": 100})
        result = []
        for f in files:
            filename = f["filename"]
            ext = os.path.splitext(filename)[1].lower()
            result.append({
                "filename": filename,
                "status": f["status"],  # added, modified, removed, renamed
                "additions": f["additions"],
                "deletions": f["deletions"],
                "changes": f["changes"],
                "language": self.EXTENSION_MAP.get(ext, "text"),
                "is_reviewable": ext in self.EXTENSION_MAP and f["status"] != "removed",
            })
        return result

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        """
        Fetch the full content of a file from a specific branch/ref.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path within the repo
            ref: Branch name or commit SHA

        Returns:
            Decoded file content as a string
        """
        data = self._get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})

        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8")
        elif "content" in data:
            return data["content"]
        else:
            # For large files, fall back to the download URL
            download_url = data.get("download_url")
            if download_url:
                resp = requests.get(download_url, headers=self.headers, timeout=30)
                resp.raise_for_status()
                return resp.text
            raise ValueError(f"Unable to fetch content for {path}")

    def get_pr_detail(self, owner: str, repo: str, pr_number: int) -> dict:
        """
        Get detailed information about a specific pull request.

        Returns:
            dict with PR details including description
        """
        pr = self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        return {
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "description": pr.get("body") or "No description",
            "created_at": pr["created_at"][:10],
            "head_branch": pr["head"]["ref"],
            "base_branch": pr["base"]["ref"],
            "html_url": pr["html_url"],
            "changed_files": pr["changed_files"],
            "additions": pr["additions"],
            "deletions": pr["deletions"],
        }

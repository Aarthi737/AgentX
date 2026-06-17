"""
AgentX — GitHub Service
Wraps PyGitHub and GitPython for all GitHub operations:
- Repository cloning
- File reading
- Branch management
- Pull Request creation with Conventional Commits
Used by: Agents 1, 6, 9.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import git
from github import Github, GithubException, Repository

from core.logging import get_logger

logger = get_logger(__name__)

# Language detection by extension
LANGUAGE_MAP: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".md": "Markdown",
    ".sql": "SQL",
    ".r": "R",
    ".ipynb": "Jupyter Notebook",
}

# Files/directories to exclude from analysis
EXCLUDE_PATTERNS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".env", "dist", "build", ".pytest_cache", ".mypy_cache",
    "*.pyc", "*.pyo", "*.egg-info", ".DS_Store",
}


class GitHubService:
    """
    Service layer for all GitHub and Git operations.
    Manages authentication, repository cloning, and PR lifecycle.
    """

    def __init__(self, token: str):
        self.token = token
        self._gh = Github(token) if token else Github()
        self._cloned_paths: List[str] = []  # track for cleanup

    def hash_token(self) -> str:
        """Return SHA-256 hash of the token (for safe storage)."""
        return hashlib.sha256(self.token.encode()).hexdigest()[:16] if self.token else ""

    def validate_repo_url(self, url: str) -> Tuple[str, str]:
        """
        Parse and validate a GitHub repository URL.
        Returns (owner, repo_name).
        Raises ValueError for invalid URLs.
        """
        url = url.strip().rstrip("/")
        # Handle both https and git@ formats
        if url.startswith("git@github.com:"):
            path = url.replace("git@github.com:", "").replace(".git", "")
        else:
            parsed = urlparse(url)
            if "github.com" not in parsed.netloc:
                raise ValueError(f"URL must be a GitHub repository: {url}")
            path = parsed.path.lstrip("/").replace(".git", "")

        parts = path.split("/")
        if len(parts) < 2:
            raise ValueError(f"Cannot parse owner/repo from URL: {url}")

        return parts[0], parts[1]

    def get_repo(self, owner: str, repo_name: str) -> Repository.Repository:
        """Fetch GitHub repository object."""
        try:
            return self._gh.get_repo(f"{owner}/{repo_name}")
        except GithubException as exc:
            raise RuntimeError(f"Cannot access repository {owner}/{repo_name}: {exc}") from exc

    def clone_repo(
        self,
        repo_url: str,
        branch: str = "main",
        base_dir: Optional[str] = None,
    ) -> str:
        """
        Clone repository to a temporary directory.
        Returns the local path to the cloned repo.
        """
        if base_dir is None:
            base_dir = tempfile.mkdtemp(prefix="agentx_")

        # Inject token into clone URL for private repos
        if self.token:
            parsed = urlparse(repo_url)
            authed_url = parsed._replace(
                netloc=f"{self.token}@{parsed.netloc}"
            ).geturl()
        else:
            authed_url = repo_url

        logger.info("cloning_repo", url=repo_url, branch=branch, dest=base_dir)

        try:
            git.Repo.clone_from(
                authed_url,
                base_dir,
                branch=branch,
                depth=50,  # shallow clone for performance
            )
        except git.GitCommandError as exc:
            # Try default branch if specified branch fails
            if branch != "main":
                try:
                    git.Repo.clone_from(authed_url, base_dir, depth=50)
                except git.GitCommandError as exc2:
                    raise RuntimeError(f"Clone failed: {exc2}") from exc2
            else:
                raise RuntimeError(f"Clone failed: {exc}") from exc

        self._cloned_paths.append(base_dir)
        logger.info("clone_complete", path=base_dir)
        return base_dir

    def build_file_manifest(self, repo_path: str) -> List[Dict]:
        """
        Walk the cloned repository and build a manifest of all analysable files.
        Returns list of {path, relative_path, language, size_bytes, line_count}.
        """
        manifest = []
        root = Path(repo_path)

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip excluded patterns
            parts = file_path.parts
            if any(part in EXCLUDE_PATTERNS for part in parts):
                continue
            if any(file_path.name.endswith(pat.lstrip("*")) for pat in EXCLUDE_PATTERNS if "*" in pat):
                continue

            ext = file_path.suffix.lower()
            language = LANGUAGE_MAP.get(ext, "Unknown")

            # Only include known code/config files
            if language == "Unknown" and ext not in (".txt", ".cfg", ".ini", ".toml"):
                continue

            try:
                content = file_path.read_text(errors="ignore")
                line_count = content.count("\n") + 1
                size = file_path.stat().st_size
            except (OSError, PermissionError):
                continue

            manifest.append(
                {
                    "path": str(file_path),
                    "relative_path": str(file_path.relative_to(root)),
                    "language": language,
                    "size_bytes": size,
                    "line_count": line_count,
                }
            )

        logger.info("manifest_built", total_files=len(manifest), repo=repo_path)
        return manifest

    def read_file(self, repo_path: str, relative_path: str) -> str:
        """Read file content from the cloned repository."""
        full_path = Path(repo_path) / relative_path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return full_path.read_text(errors="ignore")

    def create_branch(
        self,
        owner: str,
        repo_name: str,
        branch_name: str,
        base_branch: str = "main",
    ) -> str:
        """Create a new branch on GitHub for the fix PR."""
        repo = self.get_repo(owner, repo_name)
        try:
            base_ref = repo.get_branch(base_branch)
        except GithubException:
            # Fall back to default branch
            base_ref = repo.get_branch(repo.default_branch)
            base_branch = repo.default_branch

        try:
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=base_ref.commit.sha,
            )
            logger.info("branch_created", branch=branch_name, base=base_branch)
        except GithubException as exc:
            if "Reference already exists" in str(exc):
                logger.warning("branch_exists", branch=branch_name)
            else:
                raise

        return base_branch

    def commit_file(
        self,
        owner: str,
        repo_name: str,
        branch_name: str,
        file_path: str,
        new_content: str,
        commit_message: str,
    ) -> None:
        """Commit a file change to the given branch."""
        repo = self.get_repo(owner, repo_name)
        try:
            existing = repo.get_contents(file_path, ref=branch_name)
            repo.update_file(
                file_path,
                commit_message,
                new_content,
                existing.sha,
                branch=branch_name,
            )
        except GithubException as exc:
            if exc.status == 404:
                repo.create_file(file_path, commit_message, new_content, branch=branch_name)
            else:
                raise

    def create_pull_request(
        self,
        owner: str,
        repo_name: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        draft: bool = True,
    ) -> Tuple[str, int]:
        """
        Create a GitHub Pull Request.
        Returns (pr_url, pr_number).
        """
        repo = self.get_repo(owner, repo_name)
        try:
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch,
                draft=draft,
            )
            logger.info("pr_created", pr_number=pr.number, url=pr.html_url)
            return pr.html_url, pr.number
        except GithubException as exc:
            raise RuntimeError(f"Failed to create PR: {exc}") from exc

    def get_default_branch(self, owner: str, repo_name: str) -> str:
        """Return the default branch name of the repository."""
        repo = self.get_repo(owner, repo_name)
        return repo.default_branch

    def cleanup(self) -> None:
        """Remove all cloned repository directories."""
        for path in self._cloned_paths:
            try:
                shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass
        self._cloned_paths.clear()

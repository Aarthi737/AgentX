"""
AgentX — Agent 4: Security Scanner
Phase 03 — Parallel Analysis (concurrent with Agent 3)

Responsibilities:
- OWASP Top 10 vulnerability detection (A01–A10)
- Hardcoded secrets detection (API keys, passwords, tokens)
- Injection vulnerability detection (SQL, command, LDAP)
- Dependency vulnerability scanning
- Contextual code-flow analysis via Gemini for complex vulnerabilities

Tools: Bandit, Semgrep, Regex patterns, Gemini API
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import settings
from core.base_agent import BaseAgent
from core.gemini_client import get_gemini
from core.logging import get_logger
from core.state import AgentXState
from db.models import IssueType, IssueSeverity

logger = get_logger(__name__)

# ─── OWASP Top 10 Pattern Definitions (A01–A10 2021) ─────────────────────────

OWASP_PATTERNS: Dict[str, Dict] = {
    "A01_access_control": {
        "name": "Broken Access Control",
        "patterns": [
            r"is_admin\s*=\s*True",
            r"role\s*=\s*['\"]admin['\"]",
            r"if\s+user\.is_admin",
        ],
        "severity": IssueSeverity.HIGH,
        "cvss": 8.0,
    },
    "A02_cryptographic_failures": {
        "name": "Cryptographic Failure",
        "patterns": [
            r"hashlib\.md5\s*\(",
            r"hashlib\.sha1\s*\(",
            r"DES\s*\(",
            r"RC4\s*\(",
            r"ECB\s*mode",
        ],
        "severity": IssueSeverity.HIGH,
        "cvss": 7.5,
    },
    "A03_injection": {
        "name": "Injection",
        "patterns": [
            r"execute\s*\(\s*[f\"'].*%s",
            r"execute\s*\(\s*f[\"']",
            r"os\.system\s*\(",
            r"subprocess\.call\s*\(.*shell\s*=\s*True",
            r"eval\s*\(",
            r"exec\s*\(",
        ],
        "severity": IssueSeverity.CRITICAL,
        "cvss": 9.5,
    },
    "A04_insecure_design": {
        "name": "Insecure Design",
        "patterns": [
            r"debug\s*=\s*True",
            r"FLASK_DEBUG\s*=\s*1",
            r"DEBUG\s*=\s*True",
        ],
        "severity": IssueSeverity.MEDIUM,
        "cvss": 5.0,
    },
    "A05_security_misconfiguration": {
        "name": "Security Misconfiguration",
        "patterns": [
            r"host\s*=\s*['\"]0\.0\.0\.0['\"]",
            r"CORS_ALLOW_ALL",
            r"allow_origins\s*=\s*\[\s*['\"].*\*",
            r"verify\s*=\s*False",
        ],
        "severity": IssueSeverity.MEDIUM,
        "cvss": 5.5,
    },
    "A06_vulnerable_components": {
        "name": "Vulnerable and Outdated Components",
        "patterns": [
            r"requests==1\.",
            r"flask==0\.",
            r"django==1\.",
            r"numpy==1\.1[0-9]\.",
        ],
        "severity": IssueSeverity.MEDIUM,
        "cvss": 5.0,
    },
    "A07_auth_failures": {
        "name": "Identification and Authentication Failures",
        "patterns": [
            r"password\s*=\s*['\"].*['\"]",
            r"secret_key\s*=\s*['\"].*['\"]",
            r"jwt\.decode.*verify\s*=\s*False",
            r"check_password_hash\s*=\s*False",
        ],
        "severity": IssueSeverity.HIGH,
        "cvss": 8.0,
    },
    "A08_software_data_integrity": {
        "name": "Software and Data Integrity Failures",
        "patterns": [
            r"pickle\.loads\s*\(",
            r"yaml\.load\s*\(",
            r"json\.loads.*eval",
        ],
        "severity": IssueSeverity.HIGH,
        "cvss": 7.5,
    },
    "A09_logging_monitoring": {
        "name": "Security Logging and Monitoring Failures",
        "patterns": [
            r"except.*pass$",
            r"except.*: *\n.*pass",
        ],
        "severity": IssueSeverity.LOW,
        "cvss": 3.0,
    },
    "A10_ssrf": {
        "name": "Server-Side Request Forgery",
        "patterns": [
            r"requests\.get\s*\(.*user_input",
            r"urllib\.request\.urlopen\s*\(.*request\.",
        ],
        "severity": IssueSeverity.HIGH,
        "cvss": 8.0,
    },
}

# ─── Hardcoded Secret Patterns ────────────────────────────────────────────────

SECRET_PATTERNS = [
    (r"api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{20,}['\"]", "Hardcoded API Key"),
    (r"secret[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{10,}['\"]", "Hardcoded Secret Key"),
    (r"password\s*=\s*['\"][^'\"]{6,}['\"]", "Hardcoded Password"),
    (r"token\s*=\s*['\"][A-Za-z0-9_\-\.]{20,}['\"]", "Hardcoded Token"),
    (r"(?:sk|pk)[-_](?:live|test)[-_][A-Za-z0-9]{20,}", "Stripe API Key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API Key"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
]

# Gemini system prompt for security analysis
_SECURITY_SYSTEM_PROMPT = """You are a senior application security engineer specialising in code security review.
Analyse the provided code for security vulnerabilities based on OWASP Top 10 (2021).

Return a JSON object with this exact structure:
{
  "vulnerabilities": [
    {
      "title": "Short title",
      "description": "Detailed description with impact and attack vector",
      "owasp_category": "A01 through A10",
      "cwe_id": "CWE-XXX",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW | INFO",
      "line_start": 42,
      "line_end": 45,
      "code_snippet": "vulnerable code",
      "cvss_score": 8.5,
      "recommendation": "How to fix"
    }
  ]
}

Focus on real vulnerabilities. Do NOT report false positives.
Return ONLY the JSON object."""


class SecurityScannerAgent(BaseAgent):
    """
    Agent 4 — Security Scanner.
    Detects OWASP Top 10 vulnerabilities, secrets, and dependency risks.
    """

    agent_name = "SecurityScanner"
    phase = 3

    def __init__(self):
        super().__init__()
        self.gemini = get_gemini()

    async def execute(self, state: AgentXState) -> AgentXState:
        """Run all security scans concurrently."""
        repo_path = state.get("repo_local_path", "")
        file_manifest = state.get("file_manifest", [])
        run_id = state["run_id"]

        state = self._emit_progress(state, "Running security scan (OWASP + secrets + dependencies)...")

        # Focus on Python files + config files
        scan_files = [
            f for f in file_manifest
            if f["language"] in ("Python", "JavaScript", "TypeScript", "YAML", "JSON")
        ][:60]

        all_vulns: List[Dict] = []

        # Run scans concurrently
        tasks = []

        # 1. Bandit (Python-only)
        python_files = [f for f in scan_files if f["language"] == "Python"]
        if python_files:
            tasks.append(self._run_bandit(repo_path, python_files))

        # 2. Regex OWASP patterns
        tasks.append(self._regex_owasp_scan(repo_path, scan_files))

        # 3. Secret detection
        tasks.append(self._detect_secrets(repo_path, scan_files))

        # 4. Gemini contextual analysis on top security-sensitive files
        important_files = scan_files[:5]
        tasks.append(self._gemini_security_analysis(repo_path, important_files))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_vulns.extend(result)

        # Deduplicate
        seen = set()
        unique_vulns = []
        for vuln in all_vulns:
            key = (vuln.get("file_path", ""), vuln.get("line_start", 0), vuln.get("title", "")[:40])
            if key not in seen:
                seen.add(key)
                vuln["id"] = str(uuid.uuid4())
                vuln["run_id"] = run_id
                vuln["issue_type"] = IssueType.SECURITY
                unique_vulns.append(vuln)

        state["vulnerability_manifest"] = unique_vulns
        state["analysis_complete"] = True

        state = self._emit_progress(
            state,
            f"Security scan complete: {len(unique_vulns)} vulnerabilities found",
            {"vulnerability_count": len(unique_vulns)},
        )
        logger.info("security_scan_complete", run_id=run_id, vulns=len(unique_vulns))
        return state

    async def _run_bandit(self, repo_path: str, python_files: List[Dict]) -> List[Dict]:
        """Run Bandit static analyser on Python files."""
        issues = []
        try:
            result = await asyncio.create_subprocess_exec(
                "python", "-m", "bandit",
                "-r", repo_path,
                "-f", "json",
                "-q",
                "--skip", "B101,B404,B603",  # skip assert, subprocess import warnings
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(result.communicate(), timeout=60)
            data = json.loads(stdout.decode("utf-8", errors="ignore"))
            results = data.get("results", [])

            for item in results:
                severity_map = {"HIGH": IssueSeverity.HIGH, "MEDIUM": IssueSeverity.MEDIUM, "LOW": IssueSeverity.LOW}
                sev = severity_map.get(item.get("issue_severity", "MEDIUM"), IssueSeverity.MEDIUM)

                issues.append({
                    "file_path": item.get("filename", "").replace(repo_path, "").lstrip("/"),
                    "title": f"Bandit: {item.get('test_name', 'Security Issue')}",
                    "description": item.get("issue_text", ""),
                    "severity": sev,
                    "owasp_category": None,
                    "cwe_id": item.get("cwe", {}).get("id"),
                    "line_start": item.get("line_number"),
                    "line_end": item.get("line_number"),
                    "code_snippet": item.get("code", "")[:300],
                    "cvss_score": 6.0 if sev == IssueSeverity.HIGH else 4.0 if sev == IssueSeverity.MEDIUM else 2.0,
                    "research_impact_score": 4.0,
                    "detection_tool": "bandit",
                })
        except Exception as exc:
            logger.warning("bandit_failed", error=str(exc))
        return issues

    async def _regex_owasp_scan(self, repo_path: str, scan_files: List[Dict]) -> List[Dict]:
        """Regex-based OWASP Top 10 pattern scan."""
        issues = []
        for file_info in scan_files:
            full_path = Path(repo_path) / file_info["relative_path"]
            try:
                source = full_path.read_text(errors="ignore")
                lines = source.split("\n")
                for owasp_key, owasp_def in OWASP_PATTERNS.items():
                    for regex in owasp_def["patterns"]:
                        for line_no, line in enumerate(lines, start=1):
                            if line.strip().startswith("#"):
                                continue
                            if re.search(regex, line, re.IGNORECASE):
                                issues.append({
                                    "file_path": file_info["relative_path"],
                                    "title": f"OWASP {owasp_key.split('_')[0].upper()}: {owasp_def['name']}",
                                    "description": f"Potential {owasp_def['name']} vulnerability detected.",
                                    "severity": owasp_def["severity"],
                                    "owasp_category": owasp_key.split("_")[0].upper(),
                                    "cwe_id": None,
                                    "line_start": line_no,
                                    "line_end": line_no,
                                    "code_snippet": line.strip()[:300],
                                    "cvss_score": owasp_def["cvss"],
                                    "research_impact_score": 5.0,
                                    "detection_tool": "regex_owasp",
                                })
                                break
            except OSError:
                pass
        return issues

    async def _detect_secrets(self, repo_path: str, scan_files: List[Dict]) -> List[Dict]:
        """Detect hardcoded secrets, API keys, and credentials."""
        issues = []
        for file_info in scan_files:
            full_path = Path(repo_path) / file_info["relative_path"]
            try:
                source = full_path.read_text(errors="ignore")
                lines = source.split("\n")
                for pattern, secret_type in SECRET_PATTERNS:
                    for line_no, line in enumerate(lines, start=1):
                        if line.strip().startswith("#"):
                            continue
                        if re.search(pattern, line, re.IGNORECASE):
                            issues.append({
                                "file_path": file_info["relative_path"],
                                "title": f"Hardcoded Secret: {secret_type}",
                                "description": (
                                    f"Hardcoded {secret_type} found in source code. "
                                    "Use environment variables or a secrets manager."
                                ),
                                "severity": IssueSeverity.CRITICAL,
                                "owasp_category": "A07",
                                "cwe_id": "CWE-798",
                                "line_start": line_no,
                                "line_end": line_no,
                                "code_snippet": _redact_line(line.strip()),
                                "cvss_score": 9.0,
                                "research_impact_score": 6.0,
                                "detection_tool": "secret_scanner",
                            })
                            break
            except OSError:
                pass
        return issues

    async def _gemini_security_analysis(
        self, repo_path: str, files: List[Dict]
    ) -> List[Dict]:
        """Use Gemini for contextual security analysis of key files."""
        all_issues = []
        tasks = []
        for file_info in files[:5]:
            full_path = Path(repo_path) / file_info["relative_path"]
            try:
                source = full_path.read_text(errors="ignore")[:6000]
                tasks.append(self._gemini_analyse_file(source, file_info["relative_path"]))
            except OSError:
                pass

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_issues.extend(result)
        return all_issues

    async def _gemini_analyse_file(self, source: str, file_path: str) -> List[Dict]:
        """Gemini contextual security analysis for a single file."""
        try:
            result = await self.gemini.complete_structured_json(
                system_prompt=_SECURITY_SYSTEM_PROMPT,
                user_prompt=f"File: {file_path}\n\n```python\n{source}\n```\n\nAnalyse for security vulnerabilities.",
                max_tokens=2048,
            )
            vulns = result.get("vulnerabilities", [])
            enriched = []
            for v in vulns:
                enriched.append({
                    "file_path": file_path,
                    "title": v.get("title", "Security Issue"),
                    "description": v.get("description", ""),
                    "severity": v.get("severity", IssueSeverity.MEDIUM),
                    "owasp_category": v.get("owasp_category"),
                    "cwe_id": v.get("cwe_id"),
                    "line_start": v.get("line_start"),
                    "line_end": v.get("line_end"),
                    "code_snippet": v.get("code_snippet", "")[:300],
                    "cvss_score": float(v.get("cvss_score", 5.0)),
                    "research_impact_score": 5.0,
                    "detection_tool": "gemini_security",
                })
            return enriched
        except Exception as exc:
            logger.warning("gemini_security_failed", file=file_path, error=str(exc))
            return []


def _redact_line(line: str) -> str:
    """Redact secret values for safe storage in audit logs."""
    return re.sub(r"(['\"])([^'\"]{4})[^'\"]*([^'\"]{4})(['\"])", r"\1\2***\3\4", line)

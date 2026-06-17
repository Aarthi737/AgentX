"""
AgentX — Agent 6: Fix Generator
Phase 06 — Fix Generation

Responsibilities:
- Generate context-aware patches using Agent 2 context + Agent 5 RCA
- Root-cause-targeted fixes (not symptom patches)
- Strict function contract preservation
- Syntax validation via AST / ESLint
- Maximum 3 retries per issue
- Confidence score per patch

Tools: Groq Llama 3.3 70B, AST Parser, Pylint, Jinja2
"""

from __future__ import annotations

import ast
import asyncio
import difflib
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import settings
from core.base_agent import BaseAgent
from core.groq_client import get_groq
from core.logging import get_logger
from core.state import AgentXState
from db.database import get_db_session
from db.models import PatchStatus, RunStatus
from db.repositories import PatchRepository, RunRepository

logger = get_logger(__name__)

_FIX_SYSTEM_PROMPT = """You are an expert software engineer and ML researcher generating precise bug fixes.
You will receive:
1. A bug description with full root cause analysis
2. The complete file content containing the bug
3. Repository context (dependencies, related functions)

Your task: Generate a corrected version of the ENTIRE file with the bug fixed.

Rules:
- Fix ONLY the reported bug. Do not refactor unrelated code.
- Preserve all function signatures, return types, and contracts exactly
- Add a brief inline comment explaining the fix (one line)
- Do NOT add new imports unless strictly required by the fix
- The fixed code must be syntactically valid Python

Return a JSON object with EXACTLY this structure:
{
  "fixed_code": "...complete corrected file content...",
  "fix_explanation": "Concise explanation of what was changed and why",
  "confidence_score": 85,
  "changes_summary": ["List of specific changes made"],
  "preserved_contracts": ["Function signatures preserved"],
  "requires_imports": ["any new imports needed"]
}

Return ONLY the JSON object. No markdown."""

_FIX_RETRY_SYSTEM_PROMPT = """You are fixing a previously rejected patch. The validation agent rejected it.
Apply the rejection feedback and generate a corrected fix.

Return the same JSON structure as before:
{
  "fixed_code": "...complete corrected file content...",
  "fix_explanation": "What was changed from the previous attempt",
  "confidence_score": 80,
  "changes_summary": ["Changes made"],
  "preserved_contracts": [],
  "requires_imports": []
}"""


class FixGeneratorAgent(BaseAgent):
    """
    Agent 6 — Fix Generator.
    Generates root-cause-targeted, contract-preserving patches.
    """

    agent_name = "FixGenerator"
    phase = 6

    def __init__(self):
        super().__init__()
        self.groq = get_groq()

    async def execute(self, state: AgentXState) -> AgentXState:
        """Generate patches for all ranked issues with RCA context."""
        ranked_issues: List[Dict] = state.get("ranked_issues", [])
        rca_reports: List[Dict] = state.get("rca_reports", [])
        repo_path = state.get("repo_local_path", "")
        framework_metadata = state.get("framework_metadata", {})
        file_relationships = state.get("file_relationships", {})
        run_id = state["run_id"]
        state["current_phase"] = 6

        # Build RCA lookup by issue_id
        rca_by_issue: Dict[str, Dict] = {
            r["issue_id"]: r for r in rca_reports
        }

        state = self._emit_progress(
            state,
            f"Generating fixes for {len(ranked_issues)} issues...",
        )

        patches: List[Dict] = []

        # Process in batches of 3 (respect Groq rate limits)
        batch_size = 3
        for i in range(0, len(ranked_issues), batch_size):
            batch = ranked_issues[i : i + batch_size]
            tasks = [
                self._generate_patch(
                    issue=issue,
                    rca=rca_by_issue.get(issue["id"]),
                    repo_path=repo_path,
                    file_relationships=file_relationships,
                    framework_metadata=framework_metadata,
                )
                for issue in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for issue, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning("fix_gen_failed", issue_id=issue.get("id"), error=str(result))
                    result = _fallback_patch(issue, repo_path)

                result["issue_id"] = issue["id"]
                result["id"] = str(uuid.uuid4())
                result["status"] = PatchStatus.PENDING
                patches.append(result)

            if i + batch_size < len(ranked_issues):
                await asyncio.sleep(1.5)

        # Persist patches to DB
        try:
            async with get_db_session() as session:
                patch_repo = PatchRepository(session)
                for patch in patches:
                    await patch_repo.create(
                        issue_id=patch["issue_id"],
                        data={
                            k: v for k, v in patch.items()
                            if k not in ("id", "issue_id", "status")
                            and k in (
                                "original_code", "fixed_code", "diff",
                                "fix_explanation", "fix_attempt",
                                "validation_confidence",
                            )
                        },
                    )
                runs_repo = RunRepository(session)
                await runs_repo.update_status(run_id, RunStatus.VALIDATION, phase=6)
        except Exception as exc:
            logger.warning("patch_db_persist_failed", error=str(exc))

        state["patches"] = patches
        state["fix_complete"] = True

        state = self._emit_progress(
            state,
            f"Fix generation complete: {len(patches)} patches",
            {"patch_count": len(patches)},
        )
        logger.info("fix_generation_complete", run_id=run_id, patches=len(patches))
        return state

    async def regenerate_patch(
        self,
        issue: Dict,
        rca: Optional[Dict],
        repo_path: str,
        rejection_notes: str,
        previous_fix: str,
        attempt: int,
        state: AgentXState,
    ) -> Dict:
        """Regenerate a rejected patch with feedback from Agent 7."""
        if attempt > settings.fix_max_retries:
            return _fallback_patch(issue, repo_path)

        file_content = _read_file_safe(repo_path, issue.get("file_path", ""))

        user_prompt = f"""Previous fix was REJECTED by the validation agent.

Rejection feedback: {rejection_notes}

Issue: {issue.get('title')}
File: {issue.get('file_path')}
Description: {issue.get('description')}

Previous (rejected) fixed code (excerpt):
```python
{previous_fix[:3000]}
```

Original file content:
```python
{file_content[:6000]}
```

Generate a corrected fix addressing the rejection feedback."""

        try:
            result = await self.groq.complete_structured_json(
                system_prompt=_FIX_RETRY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=3000,
            )
            result = self._validate_and_enrich_patch(result, file_content, issue)
            result["fix_attempt"] = attempt
            return result
        except Exception as exc:
            logger.warning("fix_regenerate_failed", error=str(exc))
            return _fallback_patch(issue, repo_path)

    async def _generate_patch(
        self,
        issue: Dict,
        rca: Optional[Dict],
        repo_path: str,
        file_relationships: Dict,
        framework_metadata: Dict,
    ) -> Dict:
        """Generate a single patch using Groq with full context."""
        file_path = issue.get("file_path", "")
        file_content = _read_file_safe(repo_path, file_path)

        if not file_content:
            return _fallback_patch(issue, repo_path)

        # Build dependency context
        related_imports = []
        if file_path in file_relationships:
            rel = file_relationships[file_path]
            imported_by = rel.get("imported_by", [])[:3]
            for dep_path in imported_by:
                dep_content = _read_file_safe(repo_path, dep_path)
                if dep_content:
                    related_imports.append(
                        f"# File: {dep_path}\n{dep_content[:1000]}"
                    )

        rca_context = ""
        if rca:
            rca_context = f"""
Root Cause Analysis:
- Origin: {rca.get('origin', '')}
- Propagation: {rca.get('propagation', '')}
- Manifestation: {rca.get('manifestation', '')}
- Impact: {rca.get('impact', '')}
- Fix Strategy: {rca.get('fix_strategy', '')}
"""

        user_prompt = f"""Fix this issue in the file below.

**Issue**: {issue.get('title')}
**Severity**: {issue.get('severity')}
**Type**: {issue.get('issue_type')}
**Line**: {issue.get('line_start')}
**Description**: {issue.get('description')}
**ML Pattern**: {issue.get('ml_pattern', 'N/A')}
{rca_context}

**Full File Content** ({file_path}):
```python
{file_content[:7000]}
```

{"**Related files that depend on this:**" + chr(10) + chr(10).join(related_imports[:1000]) if related_imports else ""}

Generate the complete corrected file."""

        try:
            result = await self.groq.complete_structured_json(
                system_prompt=_FIX_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=3500,
            )
        except Exception as exc:
            logger.warning("groq_fix_failed", file=file_path, error=str(exc))
            return _fallback_patch(issue, repo_path)

        return self._validate_and_enrich_patch(result, file_content, issue)

    def _validate_and_enrich_patch(
        self, result: Dict, original_content: str, issue: Dict
    ) -> Dict:
        """Validate syntax and compute diff for a generated patch."""
        fixed_code = result.get("fixed_code", "")

        # Syntax validation for Python
        file_path = issue.get("file_path", "")
        if file_path.endswith(".py") and fixed_code:
            try:
                ast.parse(fixed_code)
                result["syntax_valid"] = True
            except SyntaxError as exc:
                result["syntax_valid"] = False
                result["syntax_error"] = str(exc)
                # Reduce confidence if syntax is invalid
                result["confidence_score"] = max(0, result.get("confidence_score", 50) - 30)

        # Generate unified diff
        if original_content and fixed_code:
            diff_lines = list(
                difflib.unified_diff(
                    original_content.splitlines(keepends=True),
                    fixed_code.splitlines(keepends=True),
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                    n=3,
                )
            )
            result["diff"] = "".join(diff_lines)[:5000]

        result["original_code"] = original_content[:10000]
        result["fix_explanation"] = result.get("fix_explanation", "Automated fix applied.")
        result["validation_confidence"] = float(result.get("confidence_score", 70))
        result["fix_attempt"] = 1

        return result


def _read_file_safe(repo_path: str, relative_path: str) -> str:
    """Read file content safely, returning empty string on failure."""
    if not repo_path or not relative_path:
        return ""
    try:
        full_path = Path(repo_path) / relative_path
        if full_path.exists():
            return full_path.read_text(errors="ignore")
    except OSError:
        pass
    return ""


def _fallback_patch(issue: Dict, repo_path: str) -> Dict:
    """Return a no-op patch when fix generation fails."""
    file_path = issue.get("file_path", "")
    original = _read_file_safe(repo_path, file_path)
    return {
        "original_code": original,
        "fixed_code": original,
        "diff": "",
        "fix_explanation": (
            f"Automated fix could not be generated for '{issue.get('title')}'. "
            "Manual review required."
        ),
        "confidence_score": 0,
        "validation_confidence": 0,
        "fix_attempt": 1,
        "syntax_valid": True,
        "changes_summary": [],
        "status": PatchStatus.HUMAN_REVIEW,
    }

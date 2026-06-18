"""
AgentX — Agent 8: Verification Agent (Docker Verification)
Phase 08 — Test Verification

Responsibilities:
- Auto-discover tests via Agent 2 coverage map
- Execute tests in isolated Docker containers
- Generate missing tests via Gemini when coverage gaps found
- Regression + side-effect analysis
- SAFE TO MERGE gate: NO → Human Review → Agent 6
- Coverage delta calculation

Tools: pytest, Jest, JUnit, Docker, coverage.py, Gemini API
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import settings
from core.base_agent import BaseAgent
from core.gemini_client import get_gemini
from core.logging import get_logger
from core.state import AgentXState
from db.database import get_db_session
from db.models import PatchStatus, RunStatus
from db.repositories import PatchRepository, RunRepository
from services.docker.docker_service import DockerService

logger = get_logger(__name__)

_TEST_GEN_SYSTEM_PROMPT = """You are an expert test engineer. Generate pytest unit tests for the given function/module.

Requirements:
- Cover the happy path and at least 2 edge cases
- Test the specific bug fix that was applied
- Use pytest conventions (no class required for simple tests)
- Include docstrings explaining what each test verifies
- Import only standard library + the module under test
- Do NOT use mocks unless strictly necessary

Return a JSON object:
{
  "test_code": "...complete pytest file content...",
  "test_functions": ["test_function_names"],
  "coverage_targets": ["function_names_being_tested"]
}

Return ONLY the JSON object."""


class VerificationAgent(BaseAgent):
    """
    Agent 8 — Verification.
    Executes patched code in Docker and gates merge readiness.
    """

    agent_name = "Verification"
    phase = 8

    def __init__(self):
        super().__init__()
        self.gemini = get_gemini()
        self.docker = DockerService()

    async def execute(self, state: AgentXState) -> AgentXState:
        """Run Docker verification for all approved patches."""
        validated_patches: List[Dict] = state.get("validated_patches", [])
        ranked_issues: List[Dict] = state.get("ranked_issues", [])
        test_coverage_map: Dict = state.get("test_coverage_map", {})
        framework_metadata: Dict = state.get("framework_metadata", {})
        repo_path = state.get("repo_local_path", "")
        run_id = state["run_id"]
        state["current_phase"] = 8

        # Build issue lookup
        issues_by_id = {i["id"]: i for i in ranked_issues}

        # Only verify patches that passed validation (not already in HUMAN_REVIEW)
        to_verify = [
            p for p in validated_patches
            if p.get("status") not in (PatchStatus.HUMAN_REVIEW, "HUMAN_REVIEW")
            and p.get("fixed_code")
            and p.get("fixed_code") != p.get("original_code")
        ]

        state = self._emit_progress(
            state,
            f"Running Docker verification on {len(to_verify)} patches...",
        )

        verification_results: List[Dict] = []
        overall_safe = True

        # Detect primary language for Docker runner
        languages = framework_metadata.get("languages", ["Python"])
        primary_language = languages[0] if languages else "Python"

        # Build patched files map: {relative_path: new_content}
        patched_files_map: Dict[str, str] = {}
        for patch in to_verify:
            issue = issues_by_id.get(patch.get("issue_id", ""), {})
            file_path = issue.get("file_path", "")
            if file_path and patch.get("fixed_code"):
                patched_files_map[file_path] = patch["fixed_code"]

        # Gather all relevant test files from coverage map
        relevant_tests: List[str] = []
        for file_path in patched_files_map:
            coverage_info = test_coverage_map.get(file_path, {})
            relevant_tests.extend(coverage_info.get("test_files", []))
        relevant_tests = list(set(relevant_tests))  # deduplicate

        # Generate missing tests if coverage gaps found
        generated_test_files: Dict[str, str] = {}
        if len(relevant_tests) < len(to_verify):
            state = self._emit_progress(state, "Generating missing tests...")
            for patch in to_verify[:3]:  # generate tests for top 3 uncovered patches
                issue = issues_by_id.get(patch.get("issue_id", ""), {})
                file_path = issue.get("file_path", "")
                if file_path and file_path not in {
                    f for f in relevant_tests
                }:
                    gen_result = await self._generate_tests(
                        patch=patch,
                        issue=issue,
                        repo_path=repo_path,
                    )
                    if gen_result:
                        test_filename = f"test_agentx_{uuid.uuid4().hex[:6]}.py"
                        generated_test_files[test_filename] = gen_result["test_code"]
                        relevant_tests.append(test_filename)
                        patch["tests_generated"] = len(gen_result.get("test_functions", []))

        # Merge generated tests into patched files map
        patched_files_map.update(generated_test_files)

        # Run Docker verification for all patches together
        if patched_files_map and repo_path:
            state = self._emit_progress(state, "Executing tests in Docker container...")
            docker_result = await self.docker.run_tests(
                repo_path=repo_path,
                patched_files=patched_files_map,
                test_files=relevant_tests,
                language=primary_language,
                run_id=run_id,
            )

            # Also run static analysis per patched file
            static_results = {}
            for file_path, content in list(patched_files_map.items())[:5]:
                if file_path.endswith(".py"):
                    static = await self.docker.run_static_analysis(
                        file_path=str(Path(repo_path) / file_path),
                        language="Python",
                    )
                    static_results[file_path] = static

            # Assign verification results to each patch
            for patch in to_verify:
                issue = issues_by_id.get(patch.get("issue_id", ""), {})
                file_path = issue.get("file_path", "")
                static = static_results.get(file_path, {})

                patch_result = {
                    "patch_id": patch.get("id"),
                    "issue_id": patch.get("issue_id"),
                    "file_path": file_path,
                    "tests_passed": docker_result.tests_passed,
                    "tests_failed": docker_result.tests_failed,
                    "tests_generated": patch.get("tests_generated", 0),
                    "regression_detected": docker_result.regression_detected,
                    "safe_to_merge": docker_result.safe_to_merge,
                    "verification_passed": docker_result.success,
                    "docker_output": docker_result.output[:3000],
                    "static_analysis": static,
                    "coverage_delta": docker_result.coverage_delta,
                }

                verification_results.append(patch_result)

                # Update patch object
                patch["verification_passed"] = docker_result.success
                patch["tests_passed"] = docker_result.tests_passed
                patch["tests_failed"] = docker_result.tests_failed
                patch["regression_detected"] = docker_result.regression_detected
                patch["safe_to_merge"] = docker_result.safe_to_merge
                patch["verification_report"] = patch_result

                if not docker_result.safe_to_merge:
                    overall_safe = False
                    patch["status"] = PatchStatus.HUMAN_REVIEW
                    logger.warning(
                        "patch_not_safe",
                        patch_id=patch.get("id"),
                        tests_failed=docker_result.tests_failed,
                    )

        # Patches that were already in HUMAN_REVIEW stay that way
        for patch in validated_patches:
            if patch not in to_verify:
                verification_results.append({
                    "patch_id": patch.get("id"),
                    "issue_id": patch.get("issue_id"),
                    "safe_to_merge": False,
                    "verification_passed": False,
                    "tests_passed": 0,
                    "tests_failed": 0,
                    "regression_detected": False,
                    "reason": "Skipped — patch in HUMAN_REVIEW state",
                })

        # Persist to DB
        try:
            async with get_db_session() as session:
                patch_repo = PatchRepository(session)
                for patch in validated_patches:
                    patch_id = patch.get("id")
                    if patch_id:
                        await patch_repo.update(
                            patch_id,
                            verification_passed=patch.get("verification_passed"),
                            tests_passed=patch.get("tests_passed", 0),
                            tests_failed=patch.get("tests_failed", 0),
                            tests_generated=patch.get("tests_generated", 0),
                            regression_detected=patch.get("regression_detected", False),
                            safe_to_merge=patch.get("safe_to_merge"),
                            verification_report=patch.get("verification_report"),
                            status=patch.get("status", PatchStatus.APPROVED),
                        )
                runs_repo = RunRepository(session)
                await runs_repo.update_status(run_id, RunStatus.PR_CREATED, phase=8)
        except Exception as exc:
            logger.warning("verification_db_persist_failed", error=str(exc))

        state["verification_results"] = verification_results
        state["safe_to_merge"] = overall_safe
        state["verification_complete"] = True

        safe_count = sum(1 for r in verification_results if r.get("safe_to_merge"))
        state = self._emit_progress(
            state,
            f"Verification complete: {safe_count}/{len(verification_results)} patches safe to merge",
            {
                "safe_count": safe_count,
                "total": len(verification_results),
                "overall_safe": overall_safe,
            },
        )
        logger.info(
            "verification_complete",
            run_id=run_id,
            safe=safe_count,
            total=len(verification_results),
        )
        return state

    async def _generate_tests(
        self,
        patch: Dict,
        issue: Dict,
        repo_path: str,
    ) -> Optional[Dict]:
        """Use Gemini to generate missing pytest tests for a patched function."""
        file_path = issue.get("file_path", "")
        fixed_code = patch.get("fixed_code", "")
        if not fixed_code or not file_path.endswith(".py"):
            return None

        try:
            result = await self.gemini.complete_structured_json(
                system_prompt=_TEST_GEN_SYSTEM_PROMPT,
                user_prompt=f"""Generate tests for this patched module.

Issue Fixed: {issue.get('title')}
File: {file_path}
Fix Explanation: {patch.get('fix_explanation', '')}

Patched Code:
```python
{fixed_code[:4000]}
```

Generate pytest tests that verify the fix works correctly.""",
                max_tokens=1500,
            )

            if result.get("test_code"):
                logger.info(
                    "tests_generated",
                    file=file_path,
                    count=len(result.get("test_functions", [])),
                )
                return result
        except Exception as exc:
            logger.warning("test_generation_failed", file=file_path, error=str(exc))

        return None

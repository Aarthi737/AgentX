"""
AgentX — Docker Verification Service
Manages isolated Docker container execution for Agent 8 (Verification).
Each verification run gets its own ephemeral container.
Supports Python (pytest), JavaScript (Jest), Java (JUnit).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import settings
from core.logging import get_logger

logger = get_logger(__name__)

# Language → docker image + test runner config
LANGUAGE_CONFIGS: Dict[str, Dict] = {
    "Python": {
        "image": "python:3.11-slim",
        "install_cmd": "pip install pytest pytest-cov coverage 2>/dev/null || true",
        "test_cmd": "python -m pytest {test_files} -v --tb=short --json-report --json-report-file=/tmp/test_results.json 2>&1",
        "requirements_install": "pip install -r requirements.txt 2>/dev/null || true",
        "test_file_pattern": "test_*.py",
    },
    "JavaScript": {
        "image": "node:20-slim",
        "install_cmd": "npm install 2>/dev/null || true",
        "test_cmd": "npx jest --json --outputFile=/tmp/test_results.json 2>&1",
        "requirements_install": "npm install 2>/dev/null || true",
        "test_file_pattern": "*.test.js",
    },
    "Java": {
        "image": "openjdk:17-slim",
        "install_cmd": "",
        "test_cmd": "mvn test -q 2>&1",
        "requirements_install": "",
        "test_file_pattern": "*Test.java",
    },
}


class DockerVerificationResult:
    """Result of a Docker-isolated test execution."""

    def __init__(
        self,
        success: bool,
        tests_passed: int,
        tests_failed: int,
        output: str,
        error: Optional[str] = None,
        regression_detected: bool = False,
        coverage_delta: float = 0.0,
        generated_tests: List[str] = None,
    ):
        self.success = success
        self.tests_passed = tests_passed
        self.tests_failed = tests_failed
        self.output = output
        self.error = error
        self.regression_detected = regression_detected
        self.coverage_delta = coverage_delta
        self.generated_tests = generated_tests or []
        self.safe_to_merge = success and not regression_detected

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "output": self.output[:5000],  # truncate for storage
            "error": self.error,
            "regression_detected": self.regression_detected,
            "coverage_delta": self.coverage_delta,
            "generated_tests": self.generated_tests,
            "safe_to_merge": self.safe_to_merge,
        }


class DockerService:
    """
    Manages Docker containers for isolated code verification.
    Falls back to subprocess execution if Docker is unavailable.
    """

    def __init__(self):
        self._docker_available = self._check_docker()
        logger.info("docker_service_init", docker_available=self._docker_available)

    def _check_docker(self) -> bool:
        """Check if Docker daemon is accessible."""
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return True
        except Exception:
            return False

    async def run_tests(
        self,
        repo_path: str,
        patched_files: Dict[str, str],
        test_files: List[str],
        language: str,
        run_id: str,
    ) -> DockerVerificationResult:
        """
        Apply patches to a copy of the repo, then run tests in isolation.
        Returns DockerVerificationResult.
        """
        work_dir = tempfile.mkdtemp(prefix=f"agentx_verify_{run_id}_")

        try:
            # Copy repo to working directory
            shutil.copytree(repo_path, work_dir, dirs_exist_ok=True)

            # Apply patches
            for relative_path, new_content in patched_files.items():
                target = Path(work_dir) / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new_content, encoding="utf-8")

            # Run in Docker or subprocess
            if self._docker_available:
                return await self._run_in_docker(
                    work_dir, test_files, language, run_id
                )
            else:
                logger.warning("docker_unavailable_fallback", run_id=run_id)
                return await self._run_subprocess(work_dir, test_files, language)

        except Exception as exc:
            logger.exception("docker_verify_error", run_id=run_id, error=str(exc))
            return DockerVerificationResult(
                success=False,
                tests_passed=0,
                tests_failed=0,
                output="",
                error=str(exc),
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _run_in_docker(
        self,
        work_dir: str,
        test_files: List[str],
        language: str,
        run_id: str,
    ) -> DockerVerificationResult:
        """Execute tests inside an ephemeral Docker container."""
        import docker

        config = LANGUAGE_CONFIGS.get(language, LANGUAGE_CONFIGS["Python"])
        container_name = f"agentx-verify-{run_id}-{uuid.uuid4().hex[:6]}"

        script_lines = [
            "#!/bin/bash",
            "set -e",
            "cd /workspace",
            config["requirements_install"],
            config["install_cmd"],
        ]

        if test_files:
            test_list = " ".join(test_files)
            script_lines.append(config["test_cmd"].format(test_files=test_list))
        else:
            # Run all tests
            script_lines.append(config["test_cmd"].format(test_files=""))

        script_content = "\n".join(script_lines)
        script_path = Path(work_dir) / "_agentx_run_tests.sh"
        script_path.write_text(script_content)

        client = docker.from_env()
        try:
            result = client.containers.run(
                image=config["image"],
                command="/bin/bash /workspace/_agentx_run_tests.sh",
                volumes={work_dir: {"bind": "/workspace", "mode": "rw"}},
                name=container_name,
                remove=True,
                mem_limit=settings.docker_memory_limit,
                nano_cpus=int(settings.docker_cpu_limit * 1e9),
                network_disabled=True,
                timeout=settings.docker_timeout,
                stdout=True,
                stderr=True,
            )
            output = result.decode("utf-8") if isinstance(result, bytes) else str(result)
            return self._parse_test_output(output, language, success=True)

        except docker.errors.ContainerError as exc:
            output = exc.stderr.decode("utf-8") if exc.stderr else str(exc)
            return self._parse_test_output(output, language, success=False)
        except Exception as exc:
            return DockerVerificationResult(
                success=False,
                tests_passed=0,
                tests_failed=0,
                output="",
                error=str(exc),
            )

    async def _run_subprocess(
        self,
        work_dir: str,
        test_files: List[str],
        language: str,
    ) -> DockerVerificationResult:
        """Fallback: run tests via subprocess (less isolated, for dev environments)."""
        config = LANGUAGE_CONFIGS.get(language, LANGUAGE_CONFIGS["Python"])
        test_list = " ".join(test_files) if test_files else ""
        cmd = f"cd {work_dir} && {config['install_cmd']} && {config['test_cmd'].format(test_files=test_list)}"

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=work_dir,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=settings.docker_timeout
            )
            output = stdout.decode("utf-8", errors="ignore")
            success = proc.returncode == 0
            return self._parse_test_output(output, language, success=success)
        except asyncio.TimeoutError:
            return DockerVerificationResult(
                success=False,
                tests_passed=0,
                tests_failed=0,
                output="",
                error="Verification timed out",
            )

    def _parse_test_output(
        self, output: str, language: str, success: bool
    ) -> DockerVerificationResult:
        """Parse test runner output to extract pass/fail counts."""
        passed = 0
        failed = 0

        if language == "Python":
            import re
            # pytest summary: "5 passed, 2 failed"
            match = re.search(r"(\d+) passed", output)
            if match:
                passed = int(match.group(1))
            match = re.search(r"(\d+) failed", output)
            if match:
                failed = int(match.group(1))
        elif language == "JavaScript":
            import re
            match = re.search(r"Tests:\s+(\d+) passed", output)
            if match:
                passed = int(match.group(1))
            match = re.search(r"Tests:\s+(\d+) failed", output)
            if match:
                failed = int(match.group(1))

        regression = failed > 0
        return DockerVerificationResult(
            success=success and failed == 0,
            tests_passed=passed,
            tests_failed=failed,
            output=output,
            regression_detected=regression,
        )

    async def run_static_analysis(
        self, file_path: str, language: str
    ) -> Dict:
        """
        Run Pylint + Bandit on a patched file (non-Docker, static).
        Used in Agent 8 alongside Docker execution.
        """
        results = {"pylint": None, "bandit": None, "errors": []}

        if language == "Python":
            # Pylint
            try:
                proc = await asyncio.create_subprocess_exec(
                    "python", "-m", "pylint", file_path,
                    "--output-format=json", "--score=no",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                try:
                    results["pylint"] = json.loads(stdout.decode())
                except Exception:
                    results["pylint"] = []
            except Exception as exc:
                results["errors"].append(f"pylint: {exc}")

            # Bandit
            try:
                proc = await asyncio.create_subprocess_exec(
                    "python", "-m", "bandit", "-r", file_path,
                    "-f", "json", "-q",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                try:
                    results["bandit"] = json.loads(stdout.decode())
                except Exception:
                    results["bandit"] = {}
            except Exception as exc:
                results["errors"].append(f"bandit: {exc}")

        return results

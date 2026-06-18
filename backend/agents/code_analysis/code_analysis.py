"""
AgentX — Agent 3: Code Analysis Agent
Phase 03 — Parallel Analysis (runs concurrently with Agent 4)

Responsibilities:
- Detect 8 ML-specific bug patterns:
  1. Data Leakage
  2. Missing Random Seeds
  3. Vanishing/Exploding Gradients
  4. GPU Memory Leaks
  5. Tensor Shape Mismatches
  6. Wrong Cross-Validation strategy
  7. Train/Test contamination
  8. Incorrect loss function usage
- Detect standard bugs: null dereferences, off-by-one, resource leaks, etc.
- Detect code smells
- Apply module-importance-weighted severity scoring
- Use AST for structural analysis + Gemini LLM for semantic analysis

Tools: AST, Pylint, ESLint, Gemini LLM
"""

from __future__ import annotations

import ast
import asyncio
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import settings
from core.base_agent import BaseAgent
from core.gemini_client import get_gemini
from core.logging import get_logger
from core.state import AgentXState
from db.models import IssueType, IssueSeverity

logger = get_logger(__name__)

# ─── ML Bug Pattern Definitions ───────────────────────────────────────────────

ML_PATTERNS: Dict[str, Dict] = {
    "data_leakage": {
        "name": "Data Leakage",
        "description": "Preprocessing fitted on full dataset before train/test split, leaking test information into training.",
        "severity": IssueSeverity.HIGH,
        "research_impact": 9.0,
        "cvss": 7.0,
        "patterns": [
            r"fit_transform\s*\(.*X\b",
            r"StandardScaler\(\)\.fit",
            r"MinMaxScaler\(\)\.fit",
            r"LabelEncoder\(\)\.fit",
        ],
        "ast_checks": ["fit_transform_before_split"],
    },
    "missing_random_seed": {
        "name": "Missing Random Seed",
        "description": "Stochastic operations without fixed random seed, making results non-reproducible.",
        "severity": IssueSeverity.HIGH,
        "research_impact": 8.5,
        "cvss": 5.0,
        "patterns": [
            r"train_test_split\s*\(",
            r"KFold\s*\(",
            r"RandomForest",
            r"np\.random\.",
            r"torch\.manual_seed",
        ],
        "ast_checks": ["missing_random_state_param"],
    },
    "vanishing_gradient": {
        "name": "Vanishing/Exploding Gradient",
        "description": "Activation functions or weight init patterns that cause gradient instability in deep networks.",
        "severity": IssueSeverity.MEDIUM,
        "research_impact": 7.0,
        "cvss": 4.0,
        "patterns": [
            r"activation\s*=\s*['\"]sigmoid['\"]",
            r"activation\s*=\s*['\"]tanh['\"]",
            r"sigmoid\(\)",
            r"tanh\(\)",
        ],
        "ast_checks": ["deep_network_without_batch_norm"],
    },
    "gpu_memory_leak": {
        "name": "GPU Memory Leak",
        "description": "Tensors accumulated in memory without explicit deletion, causing OOM errors in long training runs.",
        "severity": IssueSeverity.MEDIUM,
        "research_impact": 6.5,
        "cvss": 4.5,
        "patterns": [
            r"\.detach\(\)",
            r"\.cpu\(\)",
            r"torch\.cuda\.empty_cache",
        ],
        "ast_checks": ["tensor_without_detach_in_loop"],
    },
    "tensor_mismatch": {
        "name": "Tensor Shape Mismatch",
        "description": "Operations on tensors with incompatible shapes, causing silent incorrect results or runtime errors.",
        "severity": IssueSeverity.HIGH,
        "research_impact": 8.0,
        "cvss": 6.0,
        "patterns": [
            r"\.view\s*\(",
            r"\.reshape\s*\(",
            r"torch\.cat\s*\(",
            r"np\.concatenate\s*\(",
        ],
        "ast_checks": ["reshape_without_size_check"],
    },
    "wrong_cv_strategy": {
        "name": "Wrong Cross-Validation Strategy",
        "description": "Using standard KFold for time-series data, or leaking future data into past folds.",
        "severity": IssueSeverity.HIGH,
        "research_impact": 8.5,
        "cvss": 6.5,
        "patterns": [
            r"KFold\s*\(",
            r"cross_val_score\s*\(",
            r"StratifiedKFold\s*\(",
        ],
        "ast_checks": ["kfold_on_time_series"],
    },
    "train_test_contamination": {
        "name": "Train/Test Data Contamination",
        "description": "Test data used during model selection, feature engineering, or hyperparameter tuning.",
        "severity": IssueSeverity.CRITICAL,
        "research_impact": 10.0,
        "cvss": 9.0,
        "patterns": [
            r"X_test.*\.fit",
            r"y_test.*\.fit",
            r"test.*scaler\.fit",
        ],
        "ast_checks": ["test_data_in_fit_call"],
    },
    "incorrect_loss_function": {
        "name": "Incorrect Loss Function",
        "description": "Loss function inappropriate for the task (e.g., MSE for classification, BCE without sigmoid).",
        "severity": IssueSeverity.HIGH,
        "research_impact": 8.0,
        "cvss": 6.0,
        "patterns": [
            r"nn\.MSELoss",
            r"mean_squared_error",
            r"nn\.BCELoss\s*\(",
            r"binary_crossentropy",
        ],
        "ast_checks": ["loss_function_task_mismatch"],
    },
}

# ─── Standard Bug Patterns ────────────────────────────────────────────────────

STANDARD_PATTERNS = [
    {
        "id": "none_check",
        "name": "Missing None/Null Check",
        "pattern": r"\.(\w+)\s*\(",
        "severity": IssueSeverity.MEDIUM,
        "cvss": 4.0,
        "description": "Method called on potentially None object without null guard.",
    },
    {
        "id": "bare_except",
        "name": "Bare Exception Catch",
        "pattern": r"except\s*:",
        "severity": IssueSeverity.LOW,
        "cvss": 2.0,
        "description": "Bare except clause silently swallows all exceptions.",
    },
    {
        "id": "mutable_default",
        "name": "Mutable Default Argument",
        "pattern": r"def \w+\([^)]*=\s*\[\s*\]",
        "severity": IssueSeverity.MEDIUM,
        "cvss": 3.5,
        "description": "Mutable default argument shared across all function calls.",
    },
    {
        "id": "unused_variable",
        "name": "Unused Variable",
        "pattern": r"^\s*\w+\s*=\s*",
        "severity": IssueSeverity.INFO,
        "cvss": 1.0,
        "description": "Variable assigned but never used.",
    },
]

# System prompt for Gemini semantic analysis
_CODE_ANALYSIS_SYSTEM_PROMPT = """You are an expert code reviewer specialising in ML research code quality.
Analyse the provided code for bugs, ML-specific issues, and code quality problems.

Return a JSON object with this exact structure:
{
  "issues": [
    {
      "title": "Short descriptive title",
      "description": "Detailed explanation of the issue and its impact",
      "issue_type": "ML_BUG | STANDARD_BUG | CODE_SMELL",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW | INFO",
      "ml_pattern": "pattern_name_or_null",
      "line_start": 42,
      "line_end": 45,
      "code_snippet": "relevant code lines",
      "cvss_score": 7.5,
      "research_impact_score": 8.0
    }
  ]
}

Focus on:
1. The 8 ML bug patterns: data_leakage, missing_random_seed, vanishing_gradient, gpu_memory_leak,
   tensor_mismatch, wrong_cv_strategy, train_test_contamination, incorrect_loss_function
2. Standard bugs that affect correctness
3. Code patterns that would invalidate research results

Do NOT report style issues. Only report genuine bugs and ML research integrity issues.
Return ONLY the JSON object, no markdown."""


class CodeAnalysisAgent(BaseAgent):
    """
    Agent 3 — Code Analysis.
    Combines AST-based static detection with Gemini semantic analysis.
    """

    agent_name = "CodeAnalysis"
    phase = 3

    def __init__(self):
        super().__init__()
        self.gemini = get_gemini()

    async def execute(self, state: AgentXState) -> AgentXState:
        """Analyse repository for ML bugs and standard defects."""
        repo_path = state.get("repo_local_path", "")
        file_manifest = state.get("file_manifest", [])
        module_importance = state.get("module_importance", {})
        run_id = state["run_id"]

        state = self._emit_progress(state, "Running code analysis (ML patterns + standard bugs)...")

        python_files = [
            f for f in file_manifest
            if f["language"] == "Python"
            and not _is_test_file(f["relative_path"])
        ]

        python_files.sort(
            key=lambda f: module_importance.get(f["relative_path"], 0),
            reverse=True,
        )

        files_to_analyse = python_files[:50]

        all_issues: List[Dict] = []

        for file_info in files_to_analyse:
            full_path = Path(repo_path) / file_info["relative_path"]
            try:
                source = full_path.read_text(errors="ignore")
                ast_issues = self._analyse_ast(source, file_info["relative_path"])
                all_issues.extend(ast_issues)
            except Exception as exc:
                logger.warning("ast_analysis_failed", file=file_info["relative_path"], error=str(exc))

        for file_info in files_to_analyse:
            full_path = Path(repo_path) / file_info["relative_path"]
            try:
                source = full_path.read_text(errors="ignore")
                regex_issues = self._detect_ml_patterns_regex(source, file_info["relative_path"])
                all_issues.extend(regex_issues)
            except Exception as exc:
                logger.warning("regex_analysis_failed", file=file_info["relative_path"], error=str(exc))

        gemini_tasks = []
        for file_info in files_to_analyse[:10]:
            full_path = Path(repo_path) / file_info["relative_path"]
            try:
                source = full_path.read_text(errors="ignore")
                if len(source) > 8000:
                    source = source[:8000]
                gemini_tasks.append(
                    self._gemini_analyse_file(source, file_info["relative_path"])
                )
            except Exception:
                pass

        if gemini_tasks:
            gemini_results = await asyncio.gather(*gemini_tasks, return_exceptions=True)
            for result in gemini_results:
                if isinstance(result, list):
                    all_issues.extend(result)

        seen = set()
        unique_issues = []
        for issue in all_issues:
            key = (issue.get("file_path", ""), issue.get("line_start", 0), issue.get("title", "")[:40])
            if key not in seen:
                seen.add(key)
                issue["id"] = str(uuid.uuid4())
                issue["run_id"] = run_id
                unique_issues.append(issue)

        state["bug_report"] = unique_issues
        state = self._emit_progress(
            state,
            f"Code analysis complete: {len(unique_issues)} issues found",
            {"bug_count": len(unique_issues)},
        )
        logger.info("code_analysis_complete", run_id=run_id, issues=len(unique_issues))
        return state

    def _analyse_ast(self, source: str, file_path: str) -> List[Dict]:
        """Deep AST-based analysis for ML-specific bug patterns."""
        issues = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return issues

        visitor = MLBugVisitor(file_path, source)
        visitor.visit(tree)
        return visitor.issues

    def _detect_ml_patterns_regex(self, source: str, file_path: str) -> List[Dict]:
        """Regex-based fast detection for known ML anti-patterns."""
        issues = []
        lines = source.split("\n")

        for pattern_key, pattern_def in ML_PATTERNS.items():
            for regex in pattern_def["patterns"]:
                for line_no, line in enumerate(lines, start=1):
                    if re.search(regex, line):
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue

                        issues.append({
                            "file_path": file_path,
                            "title": pattern_def["name"],
                            "description": pattern_def["description"],
                            "issue_type": IssueType.ML_BUG,
                            "severity": pattern_def["severity"],
                            "ml_pattern": pattern_key,
                            "line_start": line_no,
                            "line_end": line_no,
                            "code_snippet": line.strip()[:300],
                            "cvss_score": pattern_def["cvss"],
                            "research_impact_score": pattern_def["research_impact"],
                            "detection_tool": "regex_pattern",
                        })
                        break

        return issues

    async def _gemini_analyse_file(self, source: str, file_path: str) -> List[Dict]:
        """Use Gemini LLM for semantic bug detection in a single file."""
        try:
            user_prompt = f"""File: {file_path}

```python
{source}
```

Analyse this code for ML bugs and standard defects. Return JSON only."""

            result = await self.gemini.complete_structured_json(
                system_prompt=_CODE_ANALYSIS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=2048,
            )

            raw_issues = result.get("issues", [])
            enriched = []
            for issue in raw_issues:
                if not isinstance(issue, dict):
                    continue
                enriched.append({
                    "file_path": file_path,
                    "title": issue.get("title", "Unknown Issue"),
                    "description": issue.get("description", ""),
                    "issue_type": issue.get("issue_type", IssueType.STANDARD_BUG),
                    "severity": issue.get("severity", IssueSeverity.MEDIUM),
                    "ml_pattern": issue.get("ml_pattern"),
                    "line_start": issue.get("line_start"),
                    "line_end": issue.get("line_end"),
                    "code_snippet": issue.get("code_snippet", "")[:500],
                    "cvss_score": float(issue.get("cvss_score", 5.0)),
                    "research_impact_score": float(issue.get("research_impact_score", 5.0)),
                    "detection_tool": "gemini_llm",
                })
            return enriched

        except Exception as exc:
            logger.warning("gemini_file_analysis_failed", file=file_path, error=str(exc))
            return []


# ─── AST Visitor for ML Bug Detection ────────────────────────────────────────

class MLBugVisitor(ast.NodeVisitor):
    """
    AST visitor that detects ML-specific bug patterns through structural analysis.
    More accurate than regex — understands Python semantics.
    """

    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source_lines = source.split("\n")
        self.issues: List[Dict] = []
        self._in_loop = False
        self._function_stack: List[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_stack.append(node.name)
        self._check_function(node)
        self.generic_visit(node)
        self._function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _check_function(self, node: ast.FunctionDef) -> None:
        """Check for mutable default arguments."""
        for default in node.args.defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.issues.append({
                    "file_path": self.file_path,
                    "title": "Mutable Default Argument",
                    "description": (
                        f"Function '{node.name}' uses a mutable default argument. "
                        "This is shared across all calls, causing unexpected state mutations."
                    ),
                    "issue_type": IssueType.STANDARD_BUG,
                    "severity": IssueSeverity.MEDIUM,
                    "ml_pattern": None,
                    "line_start": node.lineno,
                    "line_end": node.lineno,
                    "code_snippet": self._get_line(node.lineno),
                    "cvss_score": 3.5,
                    "research_impact_score": 4.0,
                    "detection_tool": "ast_visitor",
                })

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls for ML anti-patterns."""
        func_name = _get_call_name(node)

        # Check: train_test_split without random_state
        if func_name == "train_test_split":
            has_random_state = any(
                (isinstance(kw.arg, str) and kw.arg == "random_state")
                for kw in node.keywords
            )
            if not has_random_state:
                self.issues.append({
                    "file_path": self.file_path,
                    "title": "Missing Random Seed in train_test_split",
                    "description": (
                        "train_test_split called without random_state parameter. "
                        "Results will differ across runs, making research non-reproducible."
                    ),
                    "issue_type": IssueType.ML_BUG,
                    "severity": IssueSeverity.HIGH,
                    "ml_pattern": "missing_random_seed",
                    "line_start": node.lineno,
                    "line_end": node.lineno,
                    "code_snippet": self._get_line(node.lineno),
                    "cvss_score": 5.0,
                    "research_impact_score": 8.5,
                    "detection_tool": "ast_visitor",
                })

        # Check: fit_transform on full dataset (data leakage)
        if func_name == "fit_transform":
            self.issues.append({
                "file_path": self.file_path,
                "title": "Potential Data Leakage via fit_transform",
                "description": (
                    "fit_transform may be applied to the full dataset before splitting, "
                    "leaking test set statistics into training. Use fit on train set only, "
                    "then transform separately."
                ),
                "issue_type": IssueType.ML_BUG,
                "severity": IssueSeverity.HIGH,
                "ml_pattern": "data_leakage",
                "line_start": node.lineno,
                "line_end": node.lineno,
                "code_snippet": self._get_line(node.lineno),
                "cvss_score": 7.0,
                "research_impact_score": 9.0,
                "detection_tool": "ast_visitor",
            })

        # Check: train/test contamination — X_test.fit() or similar
        if func_name == "fit" and isinstance(node.func, ast.Attribute):
            obj = node.func.value
            if isinstance(obj, ast.Name) and "test" in obj.id.lower():
                self.issues.append({
                    "file_path": self.file_path,
                    "title": "Train/Test Data Contamination",
                    "description": (
                        f"'{obj.id}.fit()' — fitting on test data leaks test "
                        "distribution into the model. Fit on training data only."
                    ),
                    "issue_type": IssueType.ML_BUG,
                    "severity": IssueSeverity.CRITICAL,
                    "ml_pattern": "train_test_contamination",
                    "line_start": node.lineno,
                    "line_end": node.lineno,
                    "code_snippet": self._get_line(node.lineno),
                    "cvss_score": 9.0,
                    "research_impact_score": 10.0,
                    "detection_tool": "ast_visitor",
                })

        # Check: KFold without shuffle — wrong CV strategy
        if func_name == "KFold":
            has_shuffle = any(kw.arg == "shuffle" for kw in node.keywords)
            if not has_shuffle:
                self.issues.append({
                    "file_path": self.file_path,
                    "title": "KFold Without Shuffle — Possible Wrong CV Strategy",
                    "description": (
                        "KFold used without shuffle=True. For time-series data "
                        "this leaks future data into past folds."
                    ),
                    "issue_type": IssueType.ML_BUG,
                    "severity": IssueSeverity.HIGH,
                    "ml_pattern": "wrong_cv_strategy",
                    "line_start": node.lineno,
                    "line_end": node.lineno,
                    "code_snippet": self._get_line(node.lineno),
                    "cvss_score": 6.5,
                    "research_impact_score": 8.5,
                    "detection_tool": "ast_visitor",
                })

        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Detect bare except clauses."""
        if node.type is None:
            self.issues.append({
                "file_path": self.file_path,
                "title": "Bare Exception Handler",
                "description": (
                    "Bare 'except:' clause catches all exceptions including KeyboardInterrupt "
                    "and SystemExit. Specify exception types explicitly."
                ),
                "issue_type": IssueType.STANDARD_BUG,
                "severity": IssueSeverity.LOW,
                "ml_pattern": None,
                "line_start": node.lineno,
                "line_end": node.lineno,
                "code_snippet": self._get_line(node.lineno),
                "cvss_score": 2.0,
                "research_impact_score": 2.0,
                "detection_tool": "ast_visitor",
            })
        self.generic_visit(node)

    def _get_line(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()[:300]
        return ""


def _get_call_name(node: ast.Call) -> str:
    """Extract function name from a Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _is_test_file(path: str) -> bool:
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py") or "/tests/" in path
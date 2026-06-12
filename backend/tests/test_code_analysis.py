"""
Tests for Agent 3 — Code Analysis
Validates ML bug pattern detection via AST and regex.
"""

import pytest
from agents.code_analysis.code_analysis import (
    CodeAnalysisAgent,
    MLBugVisitor,
    _is_test_file,
    _get_call_name,
)
import ast


class TestMLBugDetection:
    """Tests for the 8 ML bug patterns."""

    def setup_method(self):
        self.agent = CodeAnalysisAgent()

    def _run_ast(self, source: str, file_path: str = "train.py"):
        return self.agent._analyse_ast(source, file_path)

    def _run_regex(self, source: str, file_path: str = "train.py"):
        return self.agent._detect_ml_patterns_regex(source, file_path)

    # ── Missing Random Seed ───────────────────────────────────────────────────

    def test_missing_random_seed_detected(self):
        source = "X_train, X_test = train_test_split(X, test_size=0.2)"
        issues = self._run_ast(source)
        assert any(i["ml_pattern"] == "missing_random_seed" for i in issues), \
            "Should detect missing random_state in train_test_split"

    def test_random_seed_present_no_issue(self):
        source = "X_train, X_test = train_test_split(X, test_size=0.2, random_state=42)"
        issues = self._run_ast(source)
        seed_issues = [i for i in issues if i["ml_pattern"] == "missing_random_seed"]
        assert len(seed_issues) == 0, "Should NOT flag train_test_split with random_state"

    # ── Data Leakage ──────────────────────────────────────────────────────────

    def test_data_leakage_fit_transform(self):
        source = "scaler = StandardScaler()\nX_scaled = scaler.fit_transform(X)"
        issues = self._run_ast(source)
        assert any(i["ml_pattern"] == "data_leakage" for i in issues), \
            "Should detect fit_transform as potential data leakage"

    # ── Mutable Default Argument ──────────────────────────────────────────────

    def test_mutable_default_argument(self):
        source = "def foo(x, items=[]):\n    items.append(x)\n    return items"
        issues = self._run_ast(source)
        assert any(i["title"] == "Mutable Default Argument" for i in issues)

    def test_immutable_default_no_issue(self):
        source = "def foo(x, items=None):\n    if items is None: items = []\n    return items"
        issues = self._run_ast(source)
        assert not any(i["title"] == "Mutable Default Argument" for i in issues)

    # ── Bare Except ───────────────────────────────────────────────────────────

    def test_bare_except_detected(self):
        source = "try:\n    x = 1/0\nexcept:\n    pass"
        issues = self._run_ast(source)
        assert any(i["title"] == "Bare Exception Handler" for i in issues)

    def test_specific_except_ok(self):
        source = "try:\n    x = 1/0\nexcept ZeroDivisionError:\n    pass"
        issues = self._run_ast(source)
        assert not any(i["title"] == "Bare Exception Handler" for i in issues)

    # ── Regex ML patterns ─────────────────────────────────────────────────────

    def test_regex_detects_data_leakage(self):
        source = "X_scaled = StandardScaler().fit_transform(X)\n"
        issues = self._run_regex(source)
        assert any(i["ml_pattern"] == "data_leakage" for i in issues)

    def test_commented_code_not_flagged(self):
        source = "# scaler.fit_transform(X)  # old code\n"
        issues = self._run_regex(source)
        assert len(issues) == 0, "Commented code should not be flagged"

    # ── Severity levels ───────────────────────────────────────────────────────

    def test_train_test_contamination_is_critical(self):
        from agents.code_analysis.code_analysis import ML_PATTERNS
        pattern = ML_PATTERNS["train_test_contamination"]
        from db.models import IssueSeverity
        assert pattern["severity"] == IssueSeverity.CRITICAL

    def test_data_leakage_is_high(self):
        from agents.code_analysis.code_analysis import ML_PATTERNS
        from db.models import IssueSeverity
        assert ML_PATTERNS["data_leakage"]["severity"] == IssueSeverity.HIGH


class TestHelperFunctions:
    """Tests for standalone helper functions."""

    def test_is_test_file_positive(self):
        assert _is_test_file("tests/test_train.py") is True
        assert _is_test_file("test_model.py") is True
        assert _is_test_file("model_test.py") is True

    def test_is_test_file_negative(self):
        assert _is_test_file("train.py") is False
        assert _is_test_file("model.py") is False
        assert _is_test_file("utils/helpers.py") is False

    def test_get_call_name_simple(self):
        tree = ast.parse("train_test_split(X, y)")
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _get_call_name(call) == "train_test_split"

    def test_get_call_name_attribute(self):
        tree = ast.parse("scaler.fit_transform(X)")
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _get_call_name(call) == "fit_transform"

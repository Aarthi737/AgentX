"""
AgentX — Agent 2: Repository Intelligence Agent
Phase 02 — Repository Understanding

Responsibilities:
- Build dependency graph using AST + tree-sitter
- Score module importance (centrality in dependency graph)
- Map file relationships (imports, calls, data flow)
- Identify test coverage per function
- Detect frameworks and build metadata
- Generate enriched Context Package distributed to ALL downstream agents

Tools: Python AST, tree-sitter, gitpython, networkx, Module Mapper
"""

from __future__ import annotations

import ast
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from config.settings import settings
from core.base_agent import BaseAgent
from core.logging import get_logger
from core.state import AgentXState
from db.database import get_db_session
from db.models import RunStatus
from db.repositories import ContextPackageRepository, RunRepository

logger = get_logger(__name__)

# ML framework detection signatures
ML_FRAMEWORKS = {
    "tensorflow": ["import tensorflow", "from tensorflow", "import tf"],
    "pytorch": ["import torch", "from torch"],
    "sklearn": ["from sklearn", "import sklearn"],
    "keras": ["from keras", "import keras"],
    "numpy": ["import numpy", "from numpy"],
    "pandas": ["import pandas", "from pandas"],
    "scipy": ["import scipy", "from scipy"],
    "xgboost": ["import xgboost", "from xgboost"],
    "lightgbm": ["import lightgbm", "from lightgbm"],
    "huggingface": ["from transformers", "import transformers"],
    "jax": ["import jax", "from jax"],
    "fastai": ["from fastai", "import fastai"],
}

TEST_FRAMEWORKS = {
    "Python": ["pytest", "unittest"],
    "JavaScript": ["jest", "mocha", "jasmine"],
    "Java": ["junit", "testng"],
}


class RepoIntelligenceAgent(BaseAgent):
    """
    Agent 2 — Repository Intelligence.
    Produces the Context Package that enriches every downstream agent.
    """

    agent_name = "RepoIntelligence"
    phase = 2

    async def execute(self, state: AgentXState) -> AgentXState:
        """Build full repository understanding and package it for downstream agents."""
        state["current_phase"] = 2
        repo_path = state.get("repo_local_path", "")
        file_manifest = state.get("file_manifest", [])
        run_id = state["run_id"]

        if not repo_path or not os.path.exists(repo_path):
            state["error_message"] = "Repository path not found. Ingestion must complete first."
            return state

        state = self._emit_progress(state, "Building dependency graph...")

        # ── Dependency Graph ──────────────────────────────────────────────────
        dependency_graph = await self._build_dependency_graph(repo_path, file_manifest)
        state["dependency_graph"] = self._serialize_graph(dependency_graph)

        state = self._emit_progress(state, "Scoring module importance...")

        # ── Module Importance ─────────────────────────────────────────────────
        module_importance = self._compute_module_importance(dependency_graph, file_manifest)
        state["module_importance"] = module_importance

        state = self._emit_progress(state, "Mapping file relationships...")

        # ── File Relationships ────────────────────────────────────────────────
        file_relationships = self._build_file_relationships(dependency_graph, file_manifest)
        state["file_relationships"] = file_relationships

        state = self._emit_progress(state, "Mapping test coverage...")

        # ── Test Coverage Map ─────────────────────────────────────────────────
        test_coverage_map = await self._build_test_coverage_map(repo_path, file_manifest)
        state["test_coverage_map"] = test_coverage_map

        state = self._emit_progress(state, "Detecting frameworks and metadata...")

        # ── Framework Metadata ────────────────────────────────────────────────
        framework_metadata = self._detect_framework_metadata(repo_path, file_manifest)
        state["framework_metadata"] = framework_metadata

        # ── Persist Context Package ───────────────────────────────────────────
        total_functions = sum(
            len(v) for v in test_coverage_map.values() if isinstance(v, list)
        )
        context_data = {
            "dependency_graph": state["dependency_graph"],
            "module_importance": module_importance,
            "file_relationships": file_relationships,
            "test_coverage_map": test_coverage_map,
            "framework_metadata": framework_metadata,
            "file_manifest": [
                {"path": f["relative_path"], "language": f["language"]}
                for f in file_manifest[:500]  # cap for storage
            ],
            "total_files": len(file_manifest),
            "total_functions": total_functions,
            "languages_detected": list(
                set(f["language"] for f in file_manifest if f["language"] != "Unknown")
            ),
        }

        try:
            async with get_db_session() as session:
                ctx_repo = ContextPackageRepository(session)
                pkg = await ctx_repo.save(run_id, context_data)
                state["context_package_id"] = pkg.id

                runs_repo = RunRepository(session)
                await runs_repo.update_status(
                    run_id, RunStatus.ANALYZING, phase=2
                )
        except Exception as exc:
            logger.warning("context_package_save_failed", error=str(exc))

        state["repo_intelligence_complete"] = True
        state = self._emit_progress(
            state,
            "Repository intelligence complete",
            {
                "total_files": len(file_manifest),
                "total_functions": total_functions,
                "frameworks": list(framework_metadata.get("ml_frameworks", {}).keys()),
            },
        )
        logger.info(
            "repo_intelligence_complete",
            run_id=run_id,
            files=len(file_manifest),
            functions=total_functions,
        )
        return state

    async def _build_dependency_graph(
        self, repo_path: str, file_manifest: List[Dict]
    ) -> nx.DiGraph:
        """
        Build a directed dependency graph from Python AST imports.
        Nodes = files; edges = import dependencies.
        """
        graph = nx.DiGraph()
        python_files = [f for f in file_manifest if f["language"] == "Python"]

        # Add all nodes
        for f in file_manifest:
            graph.add_node(
                f["relative_path"],
                language=f["language"],
                lines=f.get("line_count", 0),
                size=f.get("size_bytes", 0),
            )

        # Parse Python imports via AST
        for file_info in python_files:
            full_path = Path(repo_path) / file_info["relative_path"]
            try:
                source = full_path.read_text(errors="ignore")
                tree = ast.parse(source, filename=file_info["relative_path"])
                imports = _extract_imports(tree)

                for imp in imports:
                    # Try to resolve to a local file
                    resolved = _resolve_import(imp, file_info["relative_path"], file_manifest)
                    if resolved:
                        graph.add_edge(file_info["relative_path"], resolved, import_name=imp)

            except (SyntaxError, UnicodeDecodeError):
                pass

        return graph

    def _compute_module_importance(
        self, graph: nx.DiGraph, file_manifest: List[Dict]
    ) -> Dict[str, float]:
        """
        Compute importance score for each module.
        Uses PageRank on the dependency graph; normalises to [0, 1].
        Files with no dependencies get minimum score.
        """
        if len(graph.nodes) == 0:
            return {}

        try:
            pagerank = nx.pagerank(graph, alpha=0.85, max_iter=100)
        except Exception:
            # Fallback to in-degree normalised
            max_indegree = max((graph.in_degree(n) for n in graph.nodes), default=1)
            pagerank = {
                n: graph.in_degree(n) / max(max_indegree, 1) for n in graph.nodes
            }

        # Normalise to [0.1, 1.0] range
        if pagerank:
            max_score = max(pagerank.values()) or 1
            return {k: round(v / max_score, 4) for k, v in pagerank.items()}
        return {}

    def _build_file_relationships(
        self, graph: nx.DiGraph, file_manifest: List[Dict]
    ) -> Dict[str, List[str]]:
        """Map each file to its direct dependencies and dependents."""
        relationships = {}
        for node in graph.nodes:
            relationships[node] = {
                "imports": list(graph.successors(node)),
                "imported_by": list(graph.predecessors(node)),
            }
        return relationships

    async def _build_test_coverage_map(
        self, repo_path: str, file_manifest: List[Dict]
    ) -> Dict[str, Any]:
        """
        Map source functions to their test files.
        Returns {source_file: {functions: [...], test_files: [...], coverage_estimate: float}}.
        """
        coverage_map: Dict[str, Any] = {}
        python_files = [f for f in file_manifest if f["language"] == "Python"]

        # Identify test files
        test_files = {
            f["relative_path"]
            for f in python_files
            if (
                f["relative_path"].startswith("test")
                or "/test" in f["relative_path"]
                or "test_" in Path(f["relative_path"]).name
            )
        }

        for file_info in python_files:
            if file_info["relative_path"] in test_files:
                continue

            full_path = Path(repo_path) / file_info["relative_path"]
            try:
                source = full_path.read_text(errors="ignore")
                tree = ast.parse(source)
                functions = [
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
            except (SyntaxError, UnicodeDecodeError):
                functions = []

            # Find test files that reference this module
            module_name = Path(file_info["relative_path"]).stem
            related_tests = [
                tf for tf in test_files
                if module_name in tf or module_name in Path(tf).stem
            ]

            # Rough coverage estimate: if test files exist, 0.6; else 0.0
            coverage_estimate = 0.6 if related_tests else 0.0

            coverage_map[file_info["relative_path"]] = {
                "functions": functions,
                "test_files": list(related_tests),
                "coverage_estimate": coverage_estimate,
                "function_count": len(functions),
            }

        return coverage_map

    def _detect_framework_metadata(
        self, repo_path: str, file_manifest: List[Dict]
    ) -> Dict:
        """Detect ML frameworks, test runners, and project metadata."""
        detected_ml = {}
        test_runner = None
        languages = list(set(f["language"] for f in file_manifest))

        # Sample first 100 Python files for framework detection
        python_files = [f for f in file_manifest if f["language"] == "Python"][:100]

        for file_info in python_files:
            try:
                content = (
                    Path(repo_path) / file_info["relative_path"]
                ).read_text(errors="ignore")

                for framework, signatures in ML_FRAMEWORKS.items():
                    if framework not in detected_ml:
                        for sig in signatures:
                            if sig in content:
                                detected_ml[framework] = True
                                break

            except OSError:
                pass

        # Detect test runner from common config files
        root = Path(repo_path)
        for cfg in ["pytest.ini", "setup.cfg", "pyproject.toml", "tox.ini"]:
            if (root / cfg).exists():
                test_runner = "pytest"
                break
        if not test_runner and (root / "package.json").exists():
            try:
                pkg = json.loads((root / "package.json").read_text())
                scripts = pkg.get("scripts", {})
                if "jest" in str(scripts):
                    test_runner = "jest"
            except Exception:
                pass

        # Check for requirements.txt
        has_requirements = (root / "requirements.txt").exists()
        has_pyproject = (root / "pyproject.toml").exists()

        return {
            "ml_frameworks": detected_ml,
            "test_runner": test_runner or "unknown",
            "languages": languages,
            "has_requirements": has_requirements,
            "has_pyproject": has_pyproject,
            "is_ml_project": len(detected_ml) > 0,
        }

    def _serialize_graph(self, graph: nx.DiGraph) -> Dict:
        """Serialise networkx graph to JSON-safe dict."""
        return {
            "nodes": [
                {"id": node, **data}
                for node, data in graph.nodes(data=True)
            ],
            "edges": [
                {"source": u, "target": v, **data}
                for u, v, data in graph.edges(data=True)
            ],
        }


# ─── Helper functions ─────────────────────────────────────────────────────────

def _extract_imports(tree: ast.AST) -> List[str]:
    """Extract all import names from a Python AST."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _resolve_import(
    import_name: str,
    source_file: str,
    file_manifest: List[Dict],
) -> Optional[str]:
    """
    Attempt to resolve a Python import name to a local file path.
    Returns relative path or None if not found locally.
    """
    # Convert dotted import to path
    parts = import_name.split(".")
    candidates = [
        "/".join(parts) + ".py",
        "/".join(parts) + "/__init__.py",
    ]

    manifest_paths = {f["relative_path"] for f in file_manifest}
    for candidate in candidates:
        if candidate in manifest_paths:
            return candidate

    return None

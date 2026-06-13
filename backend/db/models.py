"""
AgentX — ORM Models
Complete schema for all pipeline entities stored in Supabase PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Enum,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class RunStatus(str, PyEnum):
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    REPO_INTELLIGENCE = "REPO_INTELLIGENCE"
    ANALYZING = "ANALYZING"
    RANKING = "RANKING"
    RCA = "RCA"
    FIX_GENERATION = "FIX_GENERATION"
    VALIDATION = "VALIDATION"
    VERIFICATION = "VERIFICATION"
    PR_CREATED = "PR_CREATED"
    FAILED = "FAILED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class IssueSeverity(str, PyEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class IssueType(str, PyEnum):
    ML_BUG = "ML_BUG"
    STANDARD_BUG = "STANDARD_BUG"
    SECURITY = "SECURITY"
    CODE_SMELL = "CODE_SMELL"


class PatchStatus(str, PyEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    MERGED = "MERGED"
    MODIFIED = "MODIFIED"
    CLOSED = "CLOSED"


class FeedbackOutcome(str, PyEnum):
    MERGED = "MERGED"
    MODIFIED = "MODIFIED"
    CLOSED = "CLOSED"


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Run
# ─────────────────────────────────────────────────────────────────────────────

class PipelineRun(Base):
    """
    Top-level record for a single AgentX pipeline execution.
    Created by Agent 1 (Orchestrator) at ingestion time.
    """
    __tablename__ = "pipeline_runs"
    __table_args__ = {"extend_existing": True}; __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:8]
    )
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False)
    repo_owner: Mapped[str] = mapped_column(String(255), nullable=True)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=True)
    repo_branch: Mapped[str] = mapped_column(String(255), default="main")
    github_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.PENDING, nullable=False
    )
    current_phase: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metrics
    total_issues: Mapped[int] = mapped_column(Integer, default=0)
    total_fixes: Mapped[int] = mapped_column(Integer, default=0)
    pr_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    pr_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pdf_report_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    issues: Mapped[List["Issue"]] = relationship(
        "Issue", back_populates="run", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="run", cascade="all, delete-orphan"
    )
    context_package: Mapped[Optional["ContextPackage"]] = relationship(
        "ContextPackage", back_populates="run", uselist=False, cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Context Package (Agent 2 output)
# ─────────────────────────────────────────────────────────────────────────────

class ContextPackage(Base):
    """
    Enriched repository context built by Agent 2 (Repository Intelligence).
    Shared with ALL downstream agents via LangGraph state.
    """
    __tablename__ = "context_packages"
    __table_args__ = {"extend_existing": True}; __tablename__ = "context_packages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False
    )

    dependency_graph: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    module_importance: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    file_relationships: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    test_coverage_map: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    framework_metadata: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    file_manifest: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    total_functions: Mapped[int] = mapped_column(Integer, default=0)
    languages_detected: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="context_package")


# ─────────────────────────────────────────────────────────────────────────────
# Issue (Agent 3 / 4 output, ranked by Agent 1)
# ─────────────────────────────────────────────────────────────────────────────

class Issue(Base):
    """
    A single detected bug, vulnerability, or code smell.
    Created by Agents 3 (Code Analysis) and 4 (Security Scanner).
    Ranked by the Composite Score formula in Phase 04.
    """
    __tablename__ = "issues"
    __table_args__ = {"extend_existing": True}; __tablename__ = "issues"


    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False
    )

    # Classification
    issue_type: Mapped[IssueType] = mapped_column(Enum(IssueType), nullable=False)
    severity: Mapped[IssueSeverity] = mapped_column(Enum(IssueSeverity), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Location
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    line_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    line_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    code_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Scoring (Composite Score = CVSS×0.4 + Research Impact×0.4 + Importance×0.2)
    cvss_score: Mapped[float] = mapped_column(Float, default=0.0)
    research_impact_score: Mapped[float] = mapped_column(Float, default=0.0)
    module_importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)

    # ML-specific metadata
    ml_pattern: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    owasp_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cwe_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    detection_tool: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Extra structured data
    metadata: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)


    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="issues")
    rca_report: Mapped[Optional["RCAReport"]] = relationship(
        "RCAReport", back_populates="issue", uselist=False, cascade="all, delete-orphan"
    )
    patch: Mapped[Optional["Patch"]] = relationship(
        "Patch", back_populates="issue", uselist=False, cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# RCA Report (Agent 5 output)
# ─────────────────────────────────────────────────────────────────────────────

class RCAReport(Base):
    """
    Root Cause Analysis produced by Agent 5.
    Contains the causal chain: Origin → Propagation → Manifestation → Impact.
    """

    __tablename__ = "rca_reports"
    __table_args__ = {"extend_existing": True}; __tablename__ = "rca_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )

    origin: Mapped[str] = mapped_column(Text, nullable=False)
    propagation: Mapped[str] = mapped_column(Text, nullable=False)
    manifestation: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause_summary: Mapped[str] = mapped_column(Text, nullable=False)
    research_impact_statement: Mapped[str] = mapped_column(Text, nullable=False)
    affected_functions: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    causal_chain_data: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="rca_report")


# ─────────────────────────────────────────────────────────────────────────────
# Patch (Agent 6 output, reviewed by Agents 7 & 8)
# ─────────────────────────────────────────────────────────────────────────────

class Patch(Base):
    """
    Code fix generated by Agent 6 (Fix Generator).
    Passes through Agent 7 (Validation Debate) and Agent 8 (Docker Verification).
    """
    __tablename__ = "patches"
    __table_args__ = {"extend_existing": True}; __tablename__ = "patches"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[PatchStatus] = mapped_column(
        Enum(PatchStatus), default=PatchStatus.PENDING
    )

    # Fix content
    original_code: Mapped[str] = mapped_column(Text, nullable=False)
    fixed_code: Mapped[str] = mapped_column(Text, nullable=False)
    diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fix_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    fix_attempt: Mapped[int] = mapped_column(Integer, default=1)

    # Agent 7 — Validation
    validation_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    validation_correctness: Mapped[float] = mapped_column(Float, default=0.0)
    validation_security: Mapped[float] = mapped_column(Float, default=0.0)
    validation_best_practices: Mapped[float] = mapped_column(Float, default=0.0)
    validation_research_integrity: Mapped[float] = mapped_column(Float, default=0.0)
    validation_contract_preservation: Mapped[float] = mapped_column(Float, default=0.0)
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_rounds: Mapped[int] = mapped_column(Integer, default=0)

    # Agent 8 — Docker Verification
    verification_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    tests_passed: Mapped[int] = mapped_column(Integer, default=0)
    tests_failed: Mapped[int] = mapped_column(Integer, default=0)
    tests_generated: Mapped[int] = mapped_column(Integer, default=0)
    regression_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    safe_to_merge: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    verification_report: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    issue: Mapped["Issue"] = relationship("Issue", back_populates="patch")


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log (continuous audit trail throughout pipeline)
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Immutable audit trail for every agent action.
    Written by all agents; never deleted.
    """
    __tablename__ = "audit_logs"
    __table_args__ = {"extend_existing": True}; __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phase: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # SUCCESS / FAILURE / WARNING
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="audit_logs")


# ─────────────────────────────────────────────────────────────────────────────
# Adaptive Feedback Record (Adaptive Feedback Engine)
# ─────────────────────────────────────────────────────────────────────────────

class AdaptiveFeedback(Base):
    """
    Learning signals from PR outcomes used by the Adaptive Feedback Engine.
    Merged → reinforce | Modified → partial learn | Closed → deprioritise.
    """
    __tablename__ = "adaptive_feedback"
    __table_args__ = {"extend_existing": True}; __tablename__ = "adaptive_feedback"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    pr_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    outcome: Mapped[FeedbackOutcome] = mapped_column(Enum(FeedbackOutcome), nullable=False)

    # What was learned
    issue_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ml_pattern: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fix_strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    human_modifications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Weight adjustments applied
    severity_weight_delta: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    detection_rule_updates: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    prompt_updates: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ─────────────────────────────────────────────────────────────────────────────
# Learned Weights (current state of AFE learning)
# ─────────────────────────────────────────────────────────────────────────────

class LearnedWeights(Base):
    """
    Current learned weights maintained by the Adaptive Feedback Engine.
    Single row per ml_pattern / issue_type combination.
    """
    __tablename__ = "learned_weights"
    __table_args__ = {"extend_existing": True}; __tablename__ = "learned_weights"


    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    occurrences: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )



# fix for test reloading


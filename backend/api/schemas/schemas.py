"""
AgentX — API Schemas
Pydantic v2 request/response models for all API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ── Request Models ────────────────────────────────────────────────────────────

class StartRunRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL")
    github_token: Optional[str] = Field(None, description="GitHub PAT (optional for public repos)")
    branch: str = Field(default="main", description="Branch to analyse")

    @field_validator("repo_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        if "github.com" not in v:
            raise ValueError("Only GitHub repositories are supported")
        return v.strip().rstrip("/")


class FeedbackRequest(BaseModel):
    run_id: str
    pr_number: int
    outcome: str = Field(..., pattern="^(MERGED|MODIFIED|CLOSED)$")
    human_modifications: Optional[str] = None
    issue_types: Optional[List[str]] = None
    ml_patterns: Optional[List[str]] = None


# ── Response Models ───────────────────────────────────────────────────────────

class RunStartResponse(BaseModel):
    run_id: str
    status: str
    message: str
    websocket_url: str


class IssueResponse(BaseModel):
    id: str
    issue_type: str
    severity: str
    title: str
    description: str
    file_path: str
    line_start: Optional[int]
    line_end: Optional[int]
    code_snippet: Optional[str]
    cvss_score: float
    research_impact_score: float
    composite_score: float
    rank: int
    ml_pattern: Optional[str]
    owasp_category: Optional[str]
    detection_tool: Optional[str]


class RCAResponse(BaseModel):
    id: str
    issue_id: str
    origin: str
    propagation: str
    manifestation: str
    impact: str
    root_cause_summary: str
    research_impact_statement: str
    affected_functions: List[str]


class PatchResponse(BaseModel):
    id: str
    issue_id: str
    status: str
    fix_explanation: str
    validation_confidence: float
    validation_correctness: float
    validation_security: float
    validation_best_practices: float
    validation_research_integrity: float
    validation_contract_preservation: float
    verification_passed: Optional[bool]
    tests_passed: int
    tests_failed: int
    safe_to_merge: Optional[bool]
    diff: Optional[str]


class AuditLogEntry(BaseModel):
    id: str
    agent_name: str
    phase: int
    action: str
    status: str
    message: Optional[str]
    duration_ms: Optional[int]
    created_at: datetime


class RunDetailResponse(BaseModel):
    id: str
    repo_url: str
    repo_owner: Optional[str]
    repo_name: Optional[str]
    repo_branch: str
    status: str
    current_phase: int
    total_issues: int
    total_fixes: int
    pr_url: Optional[str]
    pr_number: Optional[int]
    pdf_report_path: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    issues: List[IssueResponse] = []
    patches: List[PatchResponse] = []
    audit_logs: List[AuditLogEntry] = []


class RunListItem(BaseModel):
    id: str
    repo_url: str
    repo_owner: Optional[str]
    repo_name: Optional[str]
    status: str
    total_issues: int
    total_fixes: int
    pr_url: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


class AFEStatsResponse(BaseModel):
    total_patterns_tracked: int
    patterns: Dict[str, float]
    pending_feedback: int
    learning_rates: Dict[str, float]


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    groq: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    run_id: Optional[str] = None

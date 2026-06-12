"""Initial schema — AgentX complete database

Revision ID: 001_initial
Revises: 
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- pipeline_runs ---
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("repo_url", sa.String(512), nullable=False),
        sa.Column("repo_owner", sa.String(255), nullable=True),
        sa.Column("repo_name", sa.String(255), nullable=True),
        sa.Column("repo_branch", sa.String(255), server_default="main"),
        sa.Column("github_token_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("current_phase", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_issues", sa.Integer(), server_default="0"),
        sa.Column("total_fixes", sa.Integer(), server_default="0"),
        sa.Column("pr_url", sa.String(512), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("pdf_report_path", sa.String(512), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])

    # --- context_packages ---
    op.create_table(
        "context_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dependency_graph", postgresql.JSON(), nullable=True),
        sa.Column("module_importance", postgresql.JSON(), nullable=True),
        sa.Column("file_relationships", postgresql.JSON(), nullable=True),
        sa.Column("test_coverage_map", postgresql.JSON(), nullable=True),
        sa.Column("framework_metadata", postgresql.JSON(), nullable=True),
        sa.Column("file_manifest", postgresql.JSON(), nullable=True),
        sa.Column("total_files", sa.Integer(), server_default="0"),
        sa.Column("total_functions", sa.Integer(), server_default="0"),
        sa.Column("languages_detected", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # --- issues ---
    op.create_table(
        "issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("code_snippet", sa.Text(), nullable=True),
        sa.Column("cvss_score", sa.Float(), server_default="0"),
        sa.Column("research_impact_score", sa.Float(), server_default="0"),
        sa.Column("module_importance_score", sa.Float(), server_default="0"),
        sa.Column("composite_score", sa.Float(), server_default="0"),
        sa.Column("rank", sa.Integer(), server_default="0"),
        sa.Column("ml_pattern", sa.String(100), nullable=True),
        sa.Column("owasp_category", sa.String(100), nullable=True),
        sa.Column("cwe_id", sa.String(50), nullable=True),
        sa.Column("detection_tool", sa.String(100), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_issues_run_id", "issues", ["run_id"])
    op.create_index("ix_issues_severity", "issues", ["severity"])

    # --- rca_reports ---
    op.create_table(
        "rca_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("issue_id", sa.String(36), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("propagation", sa.Text(), nullable=False),
        sa.Column("manifestation", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=False),
        sa.Column("root_cause_summary", sa.Text(), nullable=False),
        sa.Column("research_impact_statement", sa.Text(), nullable=False),
        sa.Column("affected_functions", postgresql.JSON(), nullable=True),
        sa.Column("causal_chain_data", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # --- patches ---
    op.create_table(
        "patches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("issue_id", sa.String(36), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), server_default="PENDING"),
        sa.Column("original_code", sa.Text(), nullable=False),
        sa.Column("fixed_code", sa.Text(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("fix_explanation", sa.Text(), nullable=False),
        sa.Column("fix_attempt", sa.Integer(), server_default="1"),
        sa.Column("validation_confidence", sa.Float(), server_default="0"),
        sa.Column("validation_correctness", sa.Float(), server_default="0"),
        sa.Column("validation_security", sa.Float(), server_default="0"),
        sa.Column("validation_best_practices", sa.Float(), server_default="0"),
        sa.Column("validation_research_integrity", sa.Float(), server_default="0"),
        sa.Column("validation_contract_preservation", sa.Float(), server_default="0"),
        sa.Column("validation_notes", sa.Text(), nullable=True),
        sa.Column("validation_rounds", sa.Integer(), server_default="0"),
        sa.Column("verification_passed", sa.Boolean(), nullable=True),
        sa.Column("tests_passed", sa.Integer(), server_default="0"),
        sa.Column("tests_failed", sa.Integer(), server_default="0"),
        sa.Column("tests_generated", sa.Integer(), server_default="0"),
        sa.Column("regression_detected", sa.Boolean(), server_default="false"),
        sa.Column("safe_to_merge", sa.Boolean(), nullable=True),
        sa.Column("verification_report", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("phase", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_logs_run_id", "audit_logs", ["run_id"])

    # --- adaptive_feedback ---
    op.create_table(
        "adaptive_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("issue_type", sa.String(100), nullable=True),
        sa.Column("ml_pattern", sa.String(100), nullable=True),
        sa.Column("fix_strategy", sa.Text(), nullable=True),
        sa.Column("human_modifications", sa.Text(), nullable=True),
        sa.Column("severity_weight_delta", postgresql.JSON(), nullable=True),
        sa.Column("detection_rule_updates", postgresql.JSON(), nullable=True),
        sa.Column("prompt_updates", postgresql.JSON(), nullable=True),
        sa.Column("processed", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # --- learned_weights ---
    op.create_table(
        "learned_weights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(200), unique=True, nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0"),
        sa.Column("occurrences", sa.Integer(), server_default="0"),
        sa.Column("success_count", sa.Integer(), server_default="0"),
        sa.Column("prompt_template", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("learned_weights")
    op.drop_table("adaptive_feedback")
    op.drop_table("audit_logs")
    op.drop_table("patches")
    op.drop_table("rca_reports")
    op.drop_table("issues")
    op.drop_table("context_packages")
    op.drop_table("pipeline_runs")

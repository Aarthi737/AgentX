// AgentX Frontend — Type Definitions

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';
export type RunStatus =
  | 'PENDING' | 'INGESTING' | 'REPO_INTELLIGENCE' | 'ANALYZING'
  | 'RANKING' | 'RCA' | 'FIX_GENERATION' | 'VALIDATION'
  | 'VERIFICATION' | 'PR_CREATED' | 'FAILED' | 'HUMAN_REVIEW';
export type IssueType = 'ML_BUG' | 'STANDARD_BUG' | 'SECURITY' | 'CODE_SMELL';
export type PatchStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'HUMAN_REVIEW' | 'MERGED' | 'MODIFIED' | 'CLOSED';

export interface StartRunRequest {
  repo_url: string;
  github_token?: string;
  branch?: string;
}

export interface RunStartResponse {
  run_id: string;
  status: string;
  message: string;
  websocket_url: string;
}

export interface Issue {
  id: string;
  issue_type: IssueType;
  severity: Severity;
  title: string;
  description: string;
  file_path: string;
  line_start?: number;
  line_end?: number;
  code_snippet?: string;
  cvss_score: number;
  research_impact_score: number;
  composite_score: number;
  rank: number;
  ml_pattern?: string;
  owasp_category?: string;
  detection_tool?: string;
}

export interface Patch {
  id: string;
  issue_id: string;
  status: PatchStatus;
  fix_explanation: string;
  validation_confidence: number;
  validation_correctness: number;
  validation_security: number;
  validation_best_practices: number;
  validation_research_integrity: number;
  validation_contract_preservation: number;
  verification_passed?: boolean;
  tests_passed: number;
  tests_failed: number;
  safe_to_merge?: boolean;
  diff?: string;
}

export interface AuditLogEntry {
  id: string;
  agent_name: string;
  phase: number;
  action: string;
  status: string;
  message?: string;
  duration_ms?: number;
  created_at: string;
}

export interface RunDetail {
  id: string;
  repo_url: string;
  repo_owner?: string;
  repo_name?: string;
  repo_branch: string;
  status: RunStatus;
  current_phase: number;
  total_issues: number;
  total_fixes: number;
  pr_url?: string;
  pr_number?: number;
  pdf_report_path?: string;
  started_at: string;
  completed_at?: string;
  issues: Issue[];
  patches: Patch[];
  audit_logs: AuditLogEntry[];
}

export interface RunListItem {
  id: string;
  repo_url: string;
  repo_owner?: string;
  repo_name?: string;
  status: RunStatus;
  total_issues: number;
  total_fixes: number;
  pr_url?: string;
  started_at: string;
  completed_at?: string;
}

export interface ProgressEvent {
  type: 'progress' | 'complete' | 'error' | 'audit' | 'pong';
  run_id: string;
  agent?: string;
  phase?: number;
  message?: string;
  data?: Record<string, unknown>;
  status?: string;
  pr_url?: string;
  pr_number?: number;
  total_issues?: number;
  error?: string;
}

export interface AFEStats {
  total_patterns_tracked: number;
  patterns: Record<string, number>;
  pending_feedback: number;
  learning_rates: Record<string, number>;
}

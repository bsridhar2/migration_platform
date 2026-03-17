// src/types/index.ts
// ─── All shared TypeScript types for the migration platform UI ────────────────

export type MigrationStatus =
  | "started" | "ingesting" | "parsing" | "graphing" | "detecting"
  | "designing" | "planning" | "awaiting_approval" | "validating"
  | "generating" | "building" | "completed" | "failed";

export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface MigrationRecord {
  migration_id:    string;
  status:          MigrationStatus;
  approval_status: ApprovalStatus;
  repo_url:        string;
  created_at:      string;
  updated_at:      string;
  chunk_count?:    number;
  file_counts?:       Record<string, number>;  // embedded per type
  total_file_counts?: Record<string, number>;  // cloned per type
  soap_integration_count?: number;
  module_count?:   number;
  error_message?:  string | null;
  progress_pct:    number;
}

export interface DiagramArtifact {
  diagram_type:   string;
  title:          string;
  mermaid_source: string;
  module?:        string | null;
}

export interface SoapIntegration {
  service_name:     string;
  endpoint_url:     string;
  wsdl_url:         string;
  stub_class:       string;
  operations:       string[];
  callsite_class:   string;
  callsite_method:  string;
  migration_option: "A" | "B" | "C";
  complexity:       "LOW" | "MEDIUM" | "HIGH";
  implementation_notes?: string;
}

export interface MigrationPlan {
  roadmap: {
    phase:        string;
    task:         string;
    source_file?: string;
    target_file?: string;
    priority:     number;
  }[];
  framework_upgrades: {
    legacy:  string;
    modern:  string;
    notes?:  string;
  }[];
}

export interface BoundedContext {
  name:             string;
  description:      string;
  spring_module:    string;
  jpa_entities:     string[];
  react_components: string[];
  source_classes:   string[];
  rest_endpoints:   { method: string; path: string; response: string; auth: boolean }[];
}

export interface ArchPlan {
  bounded_contexts:  BoundedContext[];
  soap_migration_map: { service_name: string; chosen_option: string; notes: string }[];
}

export interface ArtifactsResponse {
  migration_id:     string;
  approval_status:  ApprovalStatus;
  diagrams:         DiagramArtifact[];
  soap_report:      { integrations: SoapIntegration[]; total: number; high_risk: number };
  migration_plan:   MigrationPlan;
  sequence_diagrams: DiagramArtifact[];
  arch_plan?:       ArchPlan;
  download_urls?:   Record<string, string>;
}

export interface ApprovalDecision {
  status:   "approved" | "rejected";
  comment?: string;
}

export interface ApprovalResponse {
  migration_id: string;
  status:       string;
  next_phase:   string;
  message:      string;
}

export interface StartMigrationRequest {
  repo_url:    string;
  branch?:     string;
  description?: string;
}

export interface WebSocketMessage {
  migration_id: string;
  phase:        string;
  status:       MigrationStatus;
  progress_pct: number;
  approval?:    ApprovalStatus;
  error?:       string;
}

export interface ValidationIssue {
  severity:       "CRITICAL" | "WARNING" | "INFO";
  category:       string;
  description:    string;
  file_reference: string;
  remediation:    string;
}

export interface ValidationReport {
  issues:         ValidationIssue[];
  critical_count: number;
  warning_count:  number;
  approved:       boolean;
  validated_by:   string[];
}

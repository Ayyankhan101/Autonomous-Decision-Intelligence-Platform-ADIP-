/**
 * JevCity Command Center API types
 * Synchronized with schemas/*.json and Python Pydantic definitions.
 */

export type Zone = 'north' | 'south' | 'east' | 'west' | 'central';

export type IncidentType =
  | 'accident'
  | 'fire'
  | 'flood'
  | 'traffic_spike';

export type Priority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type DecisionState =
  | 'AUTO_APPROVED'
  | 'HOLD_FOR_HUMAN'
  | 'REJECTED_INPUT'
  | 'CONTENTION_ESCALATION'
  | 'OVERRIDE_ACTIVE'
  | 'MODEL_DEGRADED';

export type DecisionSource =
  | 'laya_proposed'
  | 'policy_finalized'
  | 'fallback_rule'
  | 'human_required';

export type LayaStatus =
  | 'ok'
  | 'error'
  | 'timeout'
  | 'invalid_response'
  | 'unavailable';

export type ResourceType =
  | 'ambulance'
  | 'fire_truck'
  | 'police_unit'
  | 'flood_response_unit'
  | 'traffic_management_unit';

export type ResourceStatus = 'available' | 'assigned' | 'busy' | 'offline';

export type IncidentLifecycle =
  | 'detected'
  | 'validated'
  | 'prioritized'
  | 'resource_assigned'
  | 'active'
  | 'resolved';

export type ValidationStatus = 'valid' | 'soft_flagged' | 'hard_rejected';

export type OverrideType =
  | 'CHANGE_PRIORITY'
  | 'ASSIGN_RESOURCES'
  | 'DISMISS_INCIDENT'
  | 'ESCALATE_TO_HUMAN'
  | 'MARK_DATA_UNTRUSTED'
  | 'OVERRIDE_AUTOMATION_HOLD';

export type InjectionMode =
  | 'missing_fields'
  | 'out_of_range'
  | 'conflicting_reports'
  | 'adversarial_notes';

export type WhatIfScenario =
  | 'remove_one_ambulance'
  | 'close_road'
  | 'second_emergency';

export interface StatePayload {
  simulated_time: string;
  running: boolean;
  session_seed: number;
  scenario_seed: number;
  incident_count: number;
  decision_count: number;
  open_incident_count: number;
  available_resources: Record<ResourceType, number>;
  laya_mode: string;
  last_laya_status?: string | null;
}

export interface Resource {
  resource_id: string;
  type: ResourceType;
  zone: Zone;
  status: ResourceStatus;
  assigned_incident_id?: string | null;
}

export interface IncidentRecord {
  incident_id: string;
  incident_type: IncidentType;
  zone: Zone;
  lifecycle: IncidentLifecycle;
  validation_status: ValidationStatus;
  first_seen_simulated: string;
  latest_simulated: string;
  source_ids: string[];
  report_count: number;
  assigned_resource_ids: string[];
}

export interface ModelOutput {
  model_version: string;
  status: 'ok' | 'error' | 'timeout';
  prediction: unknown;
  confidence: number;
  latency_ms: number;
  error_code?: string | null;
}

export interface AnomalyOutput {
  data_quality_score: number;
  data_quality_reasons: string[];
  situational_anomaly: boolean;
  situational_reasons: string[];
  hard_rejected: boolean;
  status: string;
  latency_ms: number;
  model_version: string;
}

export interface SeveritySignal {
  status: string;
  prediction?: string | null;
  confidence?: number | null;
}

export interface TrafficSignal {
  status: string;
  predicted_congestion_delta?: number | null;
  confidence?: number | null;
}

export interface DataQualitySignal {
  data_quality_score: number;
  anomaly: boolean;
  reasons: string[];
}

export interface Signals {
  severity: SeveritySignal;
  traffic: TrafficSignal;
  data_quality: DataQualitySignal;
  situational_anomaly: boolean;
  anomaly?: AnomalyOutput | null;
}

export interface LayaBlock {
  status: LayaStatus;
  checkpoint: string;
  router_model: string;
  device: string;
  suggested_priority?: Priority | null;
  suggested_needs_human_review?: boolean | null;
  recommended_resource_type?: ResourceType | null;
  answer_confidence_priority?: number | null;
  distribution: Record<string, number>;
  state_hash: string;
  questions_hash: string;
  latency_ms: number;
  guardrail_applied: boolean;
  final_decision_source: DecisionSource;
}

export interface OverrideRecord {
  operator_id: string;
  override_type: OverrideType;
  reason: string;
  timestamp: string;
  previous_state: DecisionState;
  previous_priority: Priority;
}

export interface DecisionRecord {
  decision_id: string;
  incident_id: string;
  state: DecisionState;
  priority: Priority;
  policy_id: string;
  policy_version: string;
  matched_rules: string[];
  signals: Signals;
  laya?: LayaBlock | null;
  overall_confidence?: number | null;
  laya_answer_confidence?: number | null;
  recommended_resources: ResourceType[];
  assigned_resource_ids: string[];
  available_resource_ids: string[];
  reasons: string[];
  decision_time_simulated: string;
  dry_run: boolean;
  override?: OverrideRecord | null;
}

export interface AuditLayaMetadata {
  laya_checkpoint?: string | null;
  laya_router_model?: string | null;
  laya_status?: LayaStatus | null;
  laya_state_hash?: string | null;
  laya_questions_hash?: string | null;
  laya_questions_version?: string | null;
  laya_suggested_priority?: Priority | null;
  laya_answer_confidence_priority?: number | null;
  laya_latency_ms?: number | null;
  laya_guardrail_applied?: boolean | null;
  laya_final_decision_source?: DecisionSource | null;
  laya_fallback_used?: boolean | null;
  laya_guardrail_modified?: boolean | null;
}

export interface AuditEntry {
  entry_id: string;
  timestamp: string;
  actor: string;
  action: string;
  reason: string;
  before_state?: string | null;
  after_state?: string | null;
  decision_id?: string | null;
  incident_id?: string | null;
  policy_version?: string | null;
  model_versions: Record<string, string>;
  dry_run: boolean;
  laya: AuditLayaMetadata;
  previous_hash: string;
  entry_hash: string;
}

export interface IncidentResponse {
  incident: IncidentRecord;
  validation?: unknown;
  latest_decision?: DecisionRecord | null;
}

export interface WhatIfResult {
  sandbox_id: string;
  scenario: WhatIfScenario;
  dry_run: boolean;
  laya_mode: string;
  decision: DecisionRecord;
  audit_written: boolean;
  live_state_mutated: boolean;
}

export interface SimulationActionResponse {
  ok: boolean;
  incident_id?: string | null;
  decision_ids: string[];
}

import type {
  DecisionState,
  IncidentType,
  Priority,
  ResourceType,
  Zone,
} from './api';

export type AgentStatus = 'available' | 'assigned' | 'busy' | 'offline';

export interface TopologyAgent {
  id: string;
  type: ResourceType;
  zone: Zone;
  status: AgentStatus;
  position: [number, number, number];
  currentTask: string | null;
  processingLoad: number;
  decisionConfidence: number | null;
  lastDecisionId: string | null;
  lat: number | null;
  lon: number | null;
}

export interface TopologyIncident {
  id: string;
  type: IncidentType;
  zone: Zone;
  priority: Priority | null;
  state: DecisionState | null;
  position: [number, number, number];
}

export interface TopologyEdge {
  key: string;
  from: [number, number, number];
  to: [number, number, number];
  state: DecisionState | null;
  priority: Priority | null;
}

export type LogLevel = 'info' | 'ok' | 'warn' | 'error';

export interface LogLine {
  key: string;
  ts: string;
  sortKey?: number;
  level: LogLevel;
  text: string;
}

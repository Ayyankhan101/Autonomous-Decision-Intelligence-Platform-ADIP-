import type { DecisionState } from '../../types/api';
import type { Priority } from '../../types/api';

export const PRIORITY_COLOR: Record<Priority, string> = {
  LOW: '#94a3b8',
  MEDIUM: '#38bdf8',
  HIGH: '#f59e0b',
  CRITICAL: '#f43f5e',
};

export type LogLevel = 'info' | 'ok' | 'warn' | 'error';

export const DECISION_STATE_THEME: Record<DecisionState, { color: string; level: LogLevel; label: string }> = {
  AUTO_APPROVED: { color: '#22d3ee', level: 'ok', label: 'AUTO_APPROVED' },
  HOLD_FOR_HUMAN: { color: '#f59e0b', level: 'warn', label: 'HOLD_FOR_HUMAN' },
  REJECTED_INPUT: { color: '#f43f5e', level: 'error', label: 'REJECTED_INPUT' },
  CONTENTION_ESCALATION: { color: '#f43f5e', level: 'error', label: 'CONTENTION_ESCALATION' },
  OVERRIDE_ACTIVE: { color: '#a855f7', level: 'warn', label: 'OVERRIDE_ACTIVE' },
  MODEL_DEGRADED: { color: '#f6ad55', level: 'warn', label: 'MODEL_DEGRADED' },
};
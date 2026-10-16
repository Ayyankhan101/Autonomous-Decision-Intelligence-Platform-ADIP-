import { describe, expect, it } from 'vitest';
import type { DecisionState, Priority } from '../../types/api';
import { DECISION_STATE_THEME, PRIORITY_COLOR } from './theme';

const DECISION_STATES: DecisionState[] = [
  'AUTO_APPROVED',
  'HOLD_FOR_HUMAN',
  'REJECTED_INPUT',
  'CONTENTION_ESCALATION',
  'OVERRIDE_ACTIVE',
  'MODEL_DEGRADED',
];

const PRIORITIES: Priority[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

describe('DECISION_STATE_THEME', () => {
  it('covers every DecisionState exactly once', () => {
    expect(Object.keys(DECISION_STATE_THEME).sort()).toEqual([...DECISION_STATES].sort());
  });

  it('every entry has colour, level and label', () => {
    for (const state of DECISION_STATES) {
      const t = DECISION_STATE_THEME[state];
      expect(t.color).toMatch(/^#[0-9a-f]{6}$/i);
      expect(['info', 'ok', 'warn', 'error']).toContain(t.level);
      expect(t.label).toBe(state);
    }
  });
});

describe('PRIORITY_COLOR', () => {
  it('covers every Priority exactly once', () => {
    expect(Object.keys(PRIORITY_COLOR).sort()).toEqual([...PRIORITIES].sort());
  });
});

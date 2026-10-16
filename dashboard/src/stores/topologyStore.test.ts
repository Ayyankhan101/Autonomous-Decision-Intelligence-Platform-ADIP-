import { beforeEach, describe, expect, it } from 'vitest';
import { PESHAWAR_CENTER } from '../data/peshawarZones';
import type { AuditEntry, DecisionRecord, IncidentRecord, Resource, StatePayload } from '../types/api';
import { projectToScene, useTopologyStore } from './topologyStore';

const [CLAT, CLON] = PESHAWAR_CENTER;

function makeResource(over: Partial<Resource> = {}): Resource {
  return {
    resource_id: 'r1',
    type: 'ambulance',
    zone: 'central',
    status: 'available',
    ...over,
  };
}

function makeIncident(over: Partial<IncidentRecord> = {}): IncidentRecord {
  return {
    incident_id: 'i1',
    incident_type: 'fire',
    zone: 'central',
    lifecycle: 'detected',
    validation_status: 'valid',
    first_seen_simulated: '2026-01-01T00:00:00Z',
    latest_simulated: '2026-01-01T00:00:00Z',
    source_ids: ['s1'],
    report_count: 1,
    assigned_resource_ids: [],
    ...over,
  };
}

function makeDecision(over: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    decision_id: 'd1',
    incident_id: 'i1',
    state: 'AUTO_APPROVED',
    priority: 'HIGH',
    policy_id: 'p1',
    policy_version: 'v1',
    matched_rules: [],
    signals: {
      severity: { status: 'ok' },
      traffic: { status: 'ok' },
      data_quality: { data_quality_score: 1, anomaly: false, reasons: [] },
      situational_anomaly: false,
    },
    recommended_resources: [],
    assigned_resource_ids: [],
    available_resource_ids: [],
    reasons: [],
    decision_time_simulated: '2026-01-01T00:00:10Z',
    dry_run: false,
    ...over,
  };
}

function makeAudit(over: Partial<AuditEntry> = {}): AuditEntry {
  return {
    entry_id: 'a1',
    timestamp: '2026-01-01T00:00:00Z',
    actor: 'system',
    action: 'DECISION_COMMITTED',
    reason: '',
    model_versions: {},
    dry_run: false,
    laya: {},
    previous_hash: 'h0',
    entry_hash: 'h1',
    ...over,
  };
}

const emptySnapshot = {
  state: null,
  incidents: [],
  decisions: [],
  resources: [],
  auditEntries: [],
};

beforeEach(() => {
  useTopologyStore.getState().setFromDashboard(emptySnapshot);
  useTopologyStore.setState({ logs: [], selectedAgentId: null, anomalyFlashId: null });
});

describe('projectToScene', () => {
  it('maps Peshawar centre to scene origin', () => {
    const [x, y, z] = projectToScene(CLAT, CLON);
    expect(x).toBeCloseTo(0);
    expect(y).toBe(0);
    expect(z).toBeCloseTo(0);
  });

  it('east longitude maps to +x', () => {
    const [x] = projectToScene(CLAT, CLON + 0.01);
    expect(x).toBeGreaterThan(0);
  });

  it('north latitude maps to -z', () => {
    const [, , z] = projectToScene(CLAT + 0.01, CLON);
    expect(z).toBeLessThan(0);
  });
});

describe('setFromDashboard', () => {
  it('builds agents from resources, offline included', () => {
    useTopologyStore.getState().setFromDashboard({
      ...emptySnapshot,
      resources: [
        makeResource({ resource_id: 'r1' }),
        makeResource({ resource_id: 'r2', status: 'offline' }),
      ],
    });
    const { agents } = useTopologyStore.getState();
    expect(agents.map((a) => a.id)).toEqual(['r1', 'r2']);
  });

  it('keeps agent ids stable across identical snapshots', () => {
    const snap = { ...emptySnapshot, resources: [makeResource(), makeResource({ resource_id: 'r2' })] };
    useTopologyStore.getState().setFromDashboard(snap);
    const first = useTopologyStore.getState().agents.map((a) => a.id);
    useTopologyStore.getState().setFromDashboard(snap);
    const second = useTopologyStore.getState().agents.map((a) => a.id);
    expect(second).toEqual(first);
  });

  it('drops resolved incidents', () => {
    useTopologyStore.getState().setFromDashboard({
      ...emptySnapshot,
      incidents: [
        makeIncident({ incident_id: 'i1', lifecycle: 'resolved' }),
        makeIncident({ incident_id: 'i2' }),
      ],
    });
    expect(useTopologyStore.getState().incidents.map((i) => i.id)).toEqual(['i2']);
  });

  it('keeps only latest decision per incident for edges', () => {
    useTopologyStore.getState().setFromDashboard({
      ...emptySnapshot,
      incidents: [makeIncident({ incident_id: 'i1' })],
      resources: [makeResource({ resource_id: 'r1' })],
      decisions: [
        makeDecision({
          decision_id: 'd-old',
          incident_id: 'i1',
          assigned_resource_ids: ['r1'],
          decision_time_simulated: '2026-01-01T00:00:05Z',
        }),
        makeDecision({
          decision_id: 'd-new',
          incident_id: 'i1',
          assigned_resource_ids: ['r1'],
          decision_time_simulated: '2026-01-01T00:00:20Z',
        }),
      ],
    });
    const { edges } = useTopologyStore.getState();
    expect(edges).toHaveLength(1);
    expect(edges[0].key).toBe('d-new:r1');
  });

  it('skips edges for unknown resource or incident', () => {
    useTopologyStore.getState().setFromDashboard({
      ...emptySnapshot,
      incidents: [makeIncident({ incident_id: 'i1' })],
      resources: [makeResource({ resource_id: 'r1' })],
      decisions: [
        makeDecision({ incident_id: 'i-missing', assigned_resource_ids: ['r1'] }),
        makeDecision({ decision_id: 'd2', incident_id: 'i1', assigned_resource_ids: ['r-ghost'] }),
      ],
    });
    expect(useTopologyStore.getState().edges).toHaveLength(0);
  });

  it('takes first 15 audit entries (newest-first backend order)', () => {
    // Backend returns newest-first; a0 is oldest, a19 newest.
    const entries = Array.from({ length: 20 }, (_, i) =>
      makeAudit({ entry_id: `a${i}`, timestamp: `2026-01-01T00:${String(i).padStart(2, '0')}:00Z` }),
    );
    useTopologyStore.getState().setFromDashboard({ ...emptySnapshot, auditEntries: entries });
    const auditKeys = useTopologyStore
      .getState()
      .logs.filter((l) => l.key.startsWith('a:'))
      .map((l) => l.key);
    // slice(0,15) keeps a0–a14; logs then sorted newest-first → a14 first
    expect(auditKeys).toHaveLength(15);
    expect(auditKeys[0]).toBe('a:a14');
    expect(auditKeys).toContain('a:a0');
    expect(auditKeys).not.toContain('a:a15');
  });

  it('sorts merged logs newest-first by sortKey', () => {
    useTopologyStore.getState().setFromDashboard({
      ...emptySnapshot,
      incidents: [makeIncident({ incident_id: 'i1' })],
      resources: [],
      decisions: [
        makeDecision({ decision_id: 'd-old', incident_id: 'i1', decision_time_simulated: '2026-01-01T00:00:01Z' }),
        makeDecision({ decision_id: 'd-new', incident_id: 'i1', decision_time_simulated: '2026-01-01T00:00:59Z' }),
      ],
      auditEntries: [makeAudit({ entry_id: 'a1', timestamp: '2026-01-01T00:00:30Z' })],
    });
    const keys = useTopologyStore.getState().logs.map((l) => l.key);
    expect(keys).toEqual(['d:d-new', 'a:a1', 'd:d-old']);
  });

  it('preserves local: logs across refresh', () => {
    useTopologyStore.getState().pushLog({
      key: 'local:test',
      ts: '12:00:00',
      level: 'ok',
      text: 'local line',
    });
    useTopologyStore.getState().setFromDashboard({
      ...emptySnapshot,
      decisions: [makeDecision({ decision_id: 'd1', incident_id: 'i1' })],
      incidents: [makeIncident({ incident_id: 'i1' })],
    });
    const keys = useTopologyStore.getState().logs.map((l) => l.key);
    expect(keys).toContain('local:test');
    expect(keys).toContain('d:d1');
  });

  it('maps state payload fields, defaults when null', () => {
    const state: StatePayload = {
      simulated_time: '2026-01-01T12:00:00Z',
      running: true,
      session_seed: 1,
      scenario_seed: 2,
      incident_count: 0,
      decision_count: 0,
      open_incident_count: 0,
      available_resources: {} as StatePayload['available_resources'],
      laya_mode: 'live',
      feed_mode: 'live',
    };
    useTopologyStore.getState().setFromDashboard({ ...emptySnapshot, state });
    const s = useTopologyStore.getState();
    expect(s.runtimeMode).toBe('live');
    expect(s.feedMode).toBe('live');
    expect(s.simulatedTime).toBe('2026-01-01T12:00:00Z');
    expect(s.running).toBe(true);

    useTopologyStore.getState().setFromDashboard(emptySnapshot);
    const t = useTopologyStore.getState();
    expect(t.runtimeMode).toBe('mock');
    expect(t.feedMode).toBe('mock');
    expect(t.simulatedTime).toBe('');
    expect(t.running).toBe(false);
  });

  it('computes computeLoad as mean of agent base loads', () => {
    useTopologyStore.getState().setFromDashboard({
      ...emptySnapshot,
      resources: [
        makeResource({ resource_id: 'r1', status: 'available' }),
        makeResource({ resource_id: 'r2', status: 'busy' }),
      ],
    });
    // available=15, busy=85 → mean 50
    expect(useTopologyStore.getState().computeLoad).toBe(50);
  });
});

describe('pushLog', () => {
  it('assigns sortKey when missing and caps at 200', () => {
    for (let i = 0; i < 210; i++) {
      useTopologyStore.getState().pushLog({
        key: `local:${i}`,
        ts: '12:00:00',
        level: 'info',
        text: String(i),
      });
    }
    const { logs } = useTopologyStore.getState();
    expect(logs).toHaveLength(200);
    expect(logs[0].key).toBe('local:209');
    expect(logs[0].sortKey).toBeTypeOf('number');
  });
});

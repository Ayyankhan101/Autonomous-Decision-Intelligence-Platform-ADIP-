import { create } from 'zustand';
import type {
  AuditEntry,
  DecisionRecord,
  IncidentRecord,
  Resource,
  StatePayload,
} from '../types/api';
import type {
  AgentStatus,
  LogLine,
  LogLevel,
  TopologyAgent,
  TopologyEdge,
  TopologyIncident,
} from '../types/topology';
import { PESHAWAR_CENTER, zoneCentroid } from '../data/peshawarZones';

const LAT_SCALE = 95;
const LON_SCALE = 95;

const TYPE_Y: Record<string, number> = {
  ambulance: 0.6,
  fire_truck: 1.0,
  police_unit: 0.3,
  flood_response_unit: 0.15,
  traffic_management_unit: 0.8,
};

export function projectToScene(lat: number, lon: number): [number, number, number] {
  const [clat, clon] = PESHAWAR_CENTER;
  return [(lon - clon) * LON_SCALE, 0, -(lat - clat) * LAT_SCALE];
}

function baseLoad(status: AgentStatus): number {
  switch (status) {
    case 'busy':
      return 85;
    case 'assigned':
      return 55;
    case 'available':
      return 15;
    case 'offline':
      return 0;
  }
}

function agentPosition(r: Resource, zoneIndex: number, zoneCount: number): [number, number, number] {
  const y = TYPE_Y[r.type] ?? 0.4;
  if (r.lat != null && r.lon != null) {
    const [x, , z] = projectToScene(r.lat, r.lon);
    return [x, y, z];
  }
  const [clat, clon] = zoneCentroid(r.zone);
  const [x, , z] = projectToScene(clat, clon);
  const angle = (zoneIndex / Math.max(zoneCount, 1)) * Math.PI * 2;
  const ring = 1.4 + (zoneIndex % 3) * 0.5;
  return [x + Math.cos(angle) * ring, y, z + Math.sin(angle) * ring];
}

function incidentPosition(i: IncidentRecord): [number, number, number] {
  if (i.lat != null && i.lon != null) {
    const [x, , z] = projectToScene(i.lat, i.lon);
    return [x, 0.08, z];
  }
  const [clat, clon] = zoneCentroid(i.zone);
  const [x, , z] = projectToScene(clat, clon);
  return [x, 0.08, z];
}



function levelFromOverride(d: DecisionRecord): LogLevel {
  if (d.override) return 'warn';
  switch (d.state) {
    case 'AUTO_APPROVED': return 'ok';
    case 'HOLD_FOR_HUMAN': return 'warn';
    case 'REJECTED_INPUT': return 'error';
    case 'CONTENTION_ESCALATION': return 'error';
    case 'OVERRIDE_ACTIVE': return 'warn';
    case 'MODEL_DEGRADED': return 'warn';
    default: return 'info';
  }
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(11, 19);
  return d.toISOString().slice(11, 19);
}

export interface TopologyDashboardSnapshot {
  state: StatePayload | null;
  incidents: IncidentRecord[];
  decisions: DecisionRecord[];
  resources: Resource[];
  auditEntries: AuditEntry[];
}

interface TopologyState {
  agents: TopologyAgent[];
  incidents: TopologyIncident[];
  edges: TopologyEdge[];
  logs: LogLine[];
  selectedAgentId: string | null;
  simSpeed: number;
  visualPaused: boolean;
  anomalyFlashId: string | null;
  fps: number;
  computeLoad: number;
  runtimeMode: string;
  feedMode: string;
  simulatedTime: string;
  running: boolean;
  setFromDashboard: (snap: TopologyDashboardSnapshot) => void;
  selectAgent: (id: string | null) => void;
  setSimSpeed: (s: number) => void;
  setVisualPaused: (p: boolean) => void;
  setFps: (f: number) => void;
  flashAnomaly: (incidentId: string) => void;
  pushLog: (line: LogLine) => void;
}

const MAX_LOGS = 200;

export const useTopologyStore = create<TopologyState>((set, get) => ({
  agents: [],
  incidents: [],
  edges: [],
  logs: [],
  selectedAgentId: null,
  simSpeed: 1,
  visualPaused: false,
  anomalyFlashId: null,
  fps: 0,
  computeLoad: 0,
  runtimeMode: 'mock',
  feedMode: 'mock',
  simulatedTime: '',
  running: false,

  setFromDashboard: ({ state, incidents, decisions, resources, auditEntries }) => {
    const openIncidents = incidents.filter((i) => i.lifecycle !== 'resolved');

    const decisionsByResource = new Map<string, DecisionRecord>();
    for (const d of decisions) {
      for (const rid of d.assigned_resource_ids) {
        decisionsByResource.set(rid, d);
      }
    }

    const zoneSeen = new Map<string, number>();
    const zoneTotal = new Map<string, number>();
    for (const r of resources) {
      zoneTotal.set(r.zone, (zoneTotal.get(r.zone) ?? 0) + 1);
    }

    const agents: TopologyAgent[] = resources.map((r) => {
      const idx = zoneSeen.get(r.zone) ?? 0;
      zoneSeen.set(r.zone, idx + 1);
      const last = decisionsByResource.get(r.resource_id) ?? null;
      const taskIncident = r.assigned_incident_id
        ? openIncidents.find((i) => i.incident_id === r.assigned_incident_id)
        : null;
      return {
        id: r.resource_id,
        type: r.type,
        zone: r.zone,
        status: r.status,
        position: agentPosition(r, idx, zoneTotal.get(r.zone) ?? 1),
        currentTask: taskIncident
          ? `${taskIncident.incident_type} · ${taskIncident.incident_id}`
          : r.assigned_incident_id
            ? `incident ${r.assigned_incident_id}`
            : null,
        processingLoad: baseLoad(r.status),
        decisionConfidence:
          last?.overall_confidence != null
            ? Math.round(last.overall_confidence * 100)
            : null,
        lastDecisionId: last?.decision_id ?? null,
        lat: r.lat ?? null,
        lon: r.lon ?? null,
      };
    });

    const agentById = new Map(agents.map((a) => [a.id, a]));

    const tIncidents: TopologyIncident[] = openIncidents.map((i) => {
      const dec = decisions.find((d) => d.incident_id === i.incident_id) ?? null;
      return {
        id: i.incident_id,
        type: i.incident_type,
        zone: i.zone,
        priority: dec?.priority ?? null,
        state: dec?.state ?? null,
        position: incidentPosition(i),
      };
    });

    const incidentById = new Map(tIncidents.map((i) => [i.id, i]));

    // Only keep the latest decision per incident to avoid stale duplicate edges
    const latestDecisionByIncident = new Map<string, DecisionRecord>();
    for (const d of decisions) {
      const existing = latestDecisionByIncident.get(d.incident_id);
      if (
        !existing ||
        d.decision_time_simulated > existing.decision_time_simulated
      ) {
        latestDecisionByIncident.set(d.incident_id, d);
      }
    }

    const edges: TopologyEdge[] = [];
    for (const d of latestDecisionByIncident.values()) {
      const inc = incidentById.get(d.incident_id);
      if (!inc) continue;
      for (const rid of d.assigned_resource_ids) {
        const agent = agentById.get(rid);
        if (!agent) continue;
        edges.push({
          key: `${d.decision_id}:${rid}`,
          from: agent.position,
          to: inc.position,
          state: d.state,
          priority: d.priority,
        });
      }
    }

    const decisionLogs: LogLine[] = decisions.slice(-30).map((d) => ({
      key: `d:${d.decision_id}`,
      ts: fmtTime(d.decision_time_simulated),
      sortKey: new Date(d.decision_time_simulated).getTime(),
      level: levelFromOverride(d),
      text: `decision ${d.decision_id} · ${d.incident_id} · ${d.priority} · ${d.state}`,
    }));

    // Backend returns audit newest-first; take first 15 (most recent)
    const auditLogs: LogLine[] = auditEntries.slice(0, 15).map((a: AuditEntry) => ({
      key: `a:${a.entry_id}`,
      ts: fmtTime(a.timestamp),
      sortKey: new Date(a.timestamp).getTime(),
      level: a.action.includes('OVERRIDE') ? 'warn' : 'info',
      text: `audit ${a.action} · ${a.actor} · ${a.decision_id ?? a.entry_id}`,
    }));

    const localLogs = get().logs.filter((l) => l.key.startsWith('local:'));
    const merged = [...localLogs, ...decisionLogs, ...auditLogs]
      .sort((x, y) => (y.sortKey ?? 0) - (x.sortKey ?? 0))
      .slice(0, MAX_LOGS);

    const loads = agents.map((a) => a.processingLoad);
    const computeLoad = loads.length
      ? Math.round(loads.reduce((s, v) => s + v, 0) / loads.length)
      : 0;

    set({
      agents,
      incidents: tIncidents,
      edges,
      logs: merged,
      computeLoad,
      runtimeMode: state?.laya_mode ?? 'mock',
      feedMode: state?.feed_mode ?? 'mock',
      simulatedTime: state?.simulated_time ?? '',
      running: state?.running ?? false,
    });
  },

  selectAgent: (id) => set({ selectedAgentId: id }),
  setSimSpeed: (s) => set({ simSpeed: s }),
  setVisualPaused: (p) => set({ visualPaused: p }),
  setFps: (f) => set({ fps: f }),

  flashAnomaly: (incidentId) => {
    set({ anomalyFlashId: incidentId });
    window.setTimeout(() => {
      if (get().anomalyFlashId === incidentId) set({ anomalyFlashId: null });
    }, 2000);
  },

  pushLog: (line) =>
    set((s) => ({
      logs: [{ ...line, sortKey: line.sortKey ?? Date.now() }, ...s.logs].slice(0, MAX_LOGS),
    })),
}));

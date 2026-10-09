import type {
  AuditEntry,
  DecisionRecord,
  IncidentRecord,
  IncidentResponse,
  IncidentType,
  InjectionMode,
  OverrideType,
  Priority,
  Resource,
  SimulationActionResponse,
  StatePayload,
  WhatIfResult,
  WhatIfScenario,
  Zone,
} from '../types/api';

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const err = await res.json();
      detail = err.detail || JSON.stringify(err);
    } catch {
      // ignore json parse error
    }
    if (res.status >= 500) {
      throw new Error(`[${res.status}] AUDIT WRITE FAILED or server error: ${detail}`);
    }
    if (res.status === 404) {
      throw new Error(`[404] SANDBOX EXPIRED or resource not found: ${detail}`);
    }
    throw new Error(`[${res.status}] ${detail}`);
  }
  return res.json();
}

export const api = {
  // --- Reads ---
  getState: () => fetchJson<StatePayload>(`${API_BASE}/state`),

  getIncidents: async (): Promise<IncidentRecord[]> => {
    const res = await fetchJson<{ incidents: IncidentRecord[] }>(`${API_BASE}/incidents`);
    return res.incidents;
  },

  getIncident: (incidentId: string): Promise<IncidentResponse> =>
    fetchJson<IncidentResponse>(`${API_BASE}/incidents/${incidentId}`),

  getDecisions: async (): Promise<DecisionRecord[]> => {
    const res = await fetchJson<{ decisions: DecisionRecord[] }>(`${API_BASE}/decisions`);
    return res.decisions;
  },

  getDecision: (decisionId: string): Promise<DecisionRecord> =>
    fetchJson<DecisionRecord>(`${API_BASE}/decisions/${decisionId}`),

  getResources: async (): Promise<Resource[]> => {
    const res = await fetchJson<{ resources: Resource[] }>(`${API_BASE}/resources`);
    return res.resources;
  },

  getAudit: async (limit = 100): Promise<AuditEntry[]> => {
    const res = await fetchJson<{ entries: AuditEntry[] }>(`${API_BASE}/audit?limit=${limit}`);
    return res.entries;
  },

  // --- Simulation Controls ---
  startSimulation: (params?: {
    session_seed?: number;
    scenario_seed?: number;
    recording?: string | null;
    speed?: number;
  }): Promise<SimulationActionResponse> =>
    fetchJson<SimulationActionResponse>(`${API_BASE}/simulation/start`, {
      method: 'POST',
      body: JSON.stringify({
        session_seed: params?.session_seed ?? 42,
        scenario_seed: params?.scenario_seed ?? 7,
        recording: params?.recording ?? null,
        speed: params?.speed ?? 1.0,
      }),
    }),

  pauseSimulation: (): Promise<SimulationActionResponse> =>
    fetchJson<SimulationActionResponse>(`${API_BASE}/simulation/pause`, {
      method: 'POST',
    }),

  resumeSimulation: (): Promise<SimulationActionResponse> =>
    fetchJson<SimulationActionResponse>(`${API_BASE}/simulation/resume`, {
      method: 'POST',
    }),

  resetSimulation: (session_seed = 42, scenario_seed = 7): Promise<SimulationActionResponse> =>
    fetchJson<SimulationActionResponse>(`${API_BASE}/simulation/reset`, {
      method: 'POST',
      body: JSON.stringify({ session_seed, scenario_seed }),
    }),

  injectIncident: (params: {
    incident_type: IncidentType;
    zone: Zone;
    severity?: string;
    source_id?: string;
    notes?: string;
    multi_report?: boolean;
  }): Promise<SimulationActionResponse> =>
    fetchJson<SimulationActionResponse>(`${API_BASE}/simulation/incident`, {
      method: 'POST',
      body: JSON.stringify({
        incident_type: params.incident_type,
        zone: params.zone,
        severity: params.severity ?? 'moderate',
        source_id: params.source_id ?? 'sensor-dashboard-01',
        notes: params.notes || null,
        multi_report: params.multi_report ?? false,
      }),
    }),

  injectBadData: (params: {
    mode: InjectionMode;
    target_incident_id?: string | null;
  }): Promise<SimulationActionResponse> =>
    fetchJson<SimulationActionResponse>(`${API_BASE}/simulation/bad-data`, {
      method: 'POST',
      body: JSON.stringify({
        mode: params.mode,
        target_incident_id: params.target_incident_id || null,
      }),
    }),

  injectSecondEmergency: (params?: {
    incident_type?: IncidentType;
    zone?: Zone;
  }): Promise<SimulationActionResponse> =>
    fetchJson<SimulationActionResponse>(`${API_BASE}/simulation/second-emergency`, {
      method: 'POST',
      body: JSON.stringify({
        incident_type: params?.incident_type ?? 'fire',
        zone: params?.zone ?? 'north',
      }),
    }),

  // --- Overrides ---
  applyOverride: (params: {
    operator_id: string;
    decision_id: string;
    override_type: OverrideType;
    reason: string;
    new_priority?: Priority | null;
  }) =>
    fetchJson(`${API_BASE}/overrides`, {
      method: 'POST',
      body: JSON.stringify({
        operator_id: params.operator_id,
        decision_id: params.decision_id,
        override_type: params.override_type,
        reason: params.reason,
        new_priority: params.new_priority || null,
      }),
    }),

  // --- What-If ---
  runWhatIf: (scenario: WhatIfScenario, session_seed?: number): Promise<WhatIfResult> =>
    fetchJson<WhatIfResult>(`${API_BASE}/what-if/run`, {
      method: 'POST',
      body: JSON.stringify({
        scenario,
        session_seed: session_seed ?? null,
      }),
    }),

  getWhatIfResult: (sandbox_id: string): Promise<WhatIfResult> =>
    fetchJson<WhatIfResult>(`${API_BASE}/what-if/${sandbox_id}/result`),
};

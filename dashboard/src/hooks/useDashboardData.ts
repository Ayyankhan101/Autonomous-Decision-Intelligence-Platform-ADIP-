import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../services/api';
import type {
  AuditEntry,
  DecisionRecord,
  IncidentRecord,
  LatencyPoint,
  NewIds,
  Resource,
  StatePayload,
} from '../types/api';

const LATENCY_RING_MAX = 30;

export function useDashboardData(pollIntervalMs = 1500) {
  const [state, setState] = useState<StatePayload | null>(null);
  const [incidents, setIncidents] = useState<IncidentRecord[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(true);
  const [lastError, setLastError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [newIds, setNewIds] = useState<NewIds>({
    decisions: [],
    incidents: [],
    audit: [],
  });
  const [latencySeries, setLatencySeries] = useState<LatencyPoint[]>([]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const prevIdsRef = useRef<{
    decisions: Set<string>;
    incidents: Set<string>;
    audit: Set<string>;
  }>({ decisions: new Set(), incidents: new Set(), audit: new Set() });

  const fetchAll = useCallback(async () => {
    try {
      const [stateRes, incsRes, decsRes, resRes, auditRes] = await Promise.all([
        api.getState(),
        api.getIncidents(),
        api.getDecisions(),
        api.getResources(),
        api.getAudit(50),
      ]);

      setState(stateRes);
      setIncidents(incsRes);
      setDecisions(decsRes);
      setResources(resRes);
      setAuditEntries(auditRes);
      setIsConnected(true);
      setLastError(null);
      setLastUpdatedAt(Date.now());

      // NEW-row flash: set-diff against previous poll (skip first poll: no baseline)
      const prev = prevIdsRef.current;
      const hasBaseline = prev.decisions.size > 0 || prev.incidents.size > 0;
      const incIds = new Set(incsRes.map((i) => i.incident_id));
      const decIds = new Set(decsRes.map((d) => d.decision_id));
      const auditIds = new Set(auditRes.map((a) => a.entry_id));
      if (hasBaseline) {
        setNewIds({
          decisions: [...decIds].filter((id) => !prev.decisions.has(id)),
          incidents: [...incIds].filter((id) => !prev.incidents.has(id)),
          audit: [...auditIds].filter((id) => !prev.audit.has(id)),
        });
      }
      prevIdsRef.current = {
        decisions: decIds,
        incidents: incIds,
        audit: auditIds,
      };

      // Laya latency ring buffer (real per-decision latency_ms; no wall-clock)
      const latencies = decsRes
        .slice(-20)
        .map((d) => d.laya?.latency_ms)
        .filter((v): v is number => typeof v === 'number' && v >= 0);
      if (latencies.length > 0) {
        const avg = latencies.reduce((a, b) => a + b, 0) / latencies.length;
        setLatencySeries((prevSeries) => [
          ...prevSeries.slice(-(LATENCY_RING_MAX - 1)),
          { t: Date.now(), v: avg },
        ]);
      }

      // Auto-select first incident if none selected or previous disappeared
      if (incsRes.length > 0) {
        setSelectedIncidentId((prevSel) => {
          if (!prevSel || !incsRes.some((i) => i.incident_id === prevSel)) {
            return incsRes[incsRes.length - 1].incident_id;
          }
          return prevSel;
        });
      }
    } catch (err: unknown) {
      setIsConnected(false);
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
    }
  }, []);

  const manualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await fetchAll();
    setIsRefreshing(false);
  }, [fetchAll]);

  // Polling loop
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let mounted = true;
    const run = async () => {
      if (mounted) await fetchAll();
    };
    void run();

    timerRef.current = setInterval(() => {
      if (mounted) void fetchAll();
    }, pollIntervalMs);

    return () => {
      mounted = false;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchAll, pollIntervalMs]);

  const selectedIncident = incidents.find((i) => i.incident_id === selectedIncidentId) || null;
  const decisionsForSelected = decisions.filter((d) => d.incident_id === selectedIncidentId);
  const selectedDecision =
    decisionsForSelected.length > 0 ? decisionsForSelected[decisionsForSelected.length - 1] : null;

  return {
    state,
    incidents,
    decisions,
    resources,
    auditEntries,
    selectedIncidentId,
    setSelectedIncidentId,
    selectedIncident,
    selectedDecision,
    isConnected,
    lastError,
    isRefreshing,
    newIds,
    latencySeries,
    lastUpdatedAt,
    refresh: manualRefresh,
  };
}

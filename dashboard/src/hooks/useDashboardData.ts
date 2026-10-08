import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../services/api';
import type {
  AuditEntry,
  DecisionRecord,
  IncidentRecord,
  Resource,
  StatePayload,
} from '../types/api';

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

      // Auto-select first incident if none selected or previous disappeared
      if (incsRes.length > 0) {
        setSelectedIncidentId((prev) => {
          if (!prev || !incsRes.some((i) => i.incident_id === prev)) {
            return incsRes[incsRes.length - 1].incident_id;
          }
          return prev;
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
    refresh: manualRefresh,
  };
}

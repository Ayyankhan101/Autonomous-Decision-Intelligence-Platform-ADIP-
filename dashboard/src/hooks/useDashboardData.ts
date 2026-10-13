import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../services/api';
import type {
  AuditEntry,
  DecisionRecord,
  FeedsResponse,
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
  const [feeds, setFeeds] = useState<FeedsResponse | null>(null);

  const prevIdsRef = useRef<{
    decisions: Set<string>;
    incidents: Set<string>;
    audit: Set<string>;
  }>({ decisions: new Set(), incidents: new Set(), audit: new Set() });
  const sigRef = useRef<Record<string, string>>({});
  const inFlightRef = useRef(false);
  const seqRef = useRef(0);
  const lastDecCountRef = useRef(-1);

  const fetchAll = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    const mySeq = ++seqRef.current;
    try {
      const bundle = await api.getDashboard(50);
      if (mySeq !== seqRef.current) return;
      const incsRes = bundle.incidents.incidents;
      const decsRes = bundle.decisions.decisions;
      const resRes = bundle.resources.resources;
      const auditRes = bundle.audit.entries;

      const sig = {
        state: JSON.stringify(bundle.state),
        incidents: JSON.stringify(incsRes),
        decisions: JSON.stringify(decsRes),
        resources: JSON.stringify(resRes),
        audit: JSON.stringify(auditRes),
      };
      const prevSig = sigRef.current;
      if (prevSig.state !== sig.state) setState(bundle.state);
      if (prevSig.incidents !== sig.incidents) setIncidents(incsRes);
      if (prevSig.decisions !== sig.decisions) setDecisions(decsRes);
      if (prevSig.resources !== sig.resources) setResources(resRes);
      if (prevSig.audit !== sig.audit) setAuditEntries(auditRes);
      sigRef.current = sig;
      setIsConnected(true);
      setLastError(null);
      setLastUpdatedAt(Date.now());

      // Poll feeds endpoint alongside dashboard (workstream B3)
      try {
        const feedsRes = await api.getFeeds();
        if (mySeq === seqRef.current) setFeeds(feedsRes);
      } catch {
        // non-fatal: feeds endpoint down; keep last snapshot or null
      }

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

      // Laya latency ring buffer — only push when decision count changes (avoids duplicate points)
      const latencies = decsRes
        .slice(-20)
        .map((d) => d.laya?.latency_ms)
        .filter((v): v is number => typeof v === 'number' && v >= 0);
      if (latencies.length > 0 && decsRes.length !== lastDecCountRef.current) {
        lastDecCountRef.current = decsRes.length;
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
      } else {
        setSelectedIncidentId(null);
      }
    } catch (err: unknown) {
      if (mySeq !== seqRef.current) return;
      setIsConnected(false);
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
      setNewIds({ decisions: [], incidents: [], audit: [] });
    } finally {
      inFlightRef.current = false;
    }
  }, []);

  const manualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await fetchAll();
    setIsRefreshing(false);
  }, [fetchAll]);

  // Polling loop (paused while the tab is hidden)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let mounted = true;
    const stop = () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
    const start = () => {
      stop();
      timerRef.current = setInterval(() => {
        if (mounted) void fetchAll();
      }, pollIntervalMs);
    };
    const run = async () => {
      if (mounted) await fetchAll();
    };
    const onVisibility = () => {
      if (!mounted) return;
      if (document.visibilityState === 'hidden') {
        stop();
      } else {
        void run();
        start();
      }
    };

    void run();
    if (document.visibilityState === 'visible') start();
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      mounted = false;
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
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
    feeds,
    refresh: manualRefresh,
  };
}

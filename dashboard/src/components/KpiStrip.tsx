import type React from 'react';
import { useState } from 'react';
import { Activity, Timer, Layers, Gauge } from 'lucide-react';
import type {
  DecisionRecord,
  IncidentRecord,
  LatencyPoint,
  Resource,
  StatePayload,
} from '../types/api';
import { Sparkline } from './Sparkline';

interface KpiStripProps {
  state: StatePayload | null;
  incidents: IncidentRecord[];
  decisions: DecisionRecord[];
  resources: Resource[];
  latencySeries: LatencyPoint[];
}

function KpiCard({
  icon,
  label,
  value,
  sub,
  accent,
  delta,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: React.ReactNode;
  accent: string;
  delta?: number | null;
}) {
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl px-4 py-3 flex items-center justify-between gap-3 flex-1 min-w-0">
      <div className="flex items-center gap-2.5 min-w-0">
        <div className={`p-1.5 rounded-md bg-slate-950 border border-slate-800 ${accent}`}>
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
            {label}
          </div>
          <div className="text-lg font-bold text-slate-100 font-mono leading-tight">
            {value}
            {delta != null && delta !== 0 && (
              <span
                className={`ml-1.5 text-[10px] font-mono ${
                  delta > 0 ? 'text-rose-400' : 'text-emerald-400'
                }`}
              >
                {delta > 0 ? '▲' : '▼'}{Math.abs(delta)}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex flex-col items-end gap-1">
        {sub}
      </div>
    </div>
  );
}

const HIST_MAX = 40;

function useHistory(value: number): number[] {
  const [hist, setHist] = useState<number[]>([]);
  const [prevValue, setPrevValue] = useState<number | undefined>(undefined);
  if (prevValue !== value) {
    setPrevValue(value);
    setHist((h) => {
      if (h.length > 0 && h[h.length - 1] === value) return h;
      const next = [...h, value];
      if (next.length > HIST_MAX) next.shift();
      return next;
    });
  }
  return hist;
}

export const KpiStrip: React.FC<KpiStripProps> = ({
  state,
  incidents,
  decisions,
  resources,
  latencySeries,
}) => {
  const open = state?.open_incident_count ?? incidents.length;
  const total = resources.length || 1;
  const busy = resources.filter((r) => r.status === 'assigned' || r.status === 'busy').length;
  const utilPct = Math.round((busy / total) * 100);
  const latencies = latencySeries.map((p) => p.v);
  const lastLatency = latencies.length > 0 ? latencies[latencies.length - 1] : null;

  const openHist = useHistory(open);
  const decisionHist = useHistory(decisions.length);
  const utilHist = useHistory(utilPct);

  const prev = (h: number[]) => (h.length >= 2 ? h[h.length - 2] : null);
  const dOpen = prev(openHist) !== null ? open - prev(openHist)! : null;
  const dDec = prev(decisionHist) !== null ? decisions.length - prev(decisionHist)! : null;
  const dUtil = prev(utilHist) !== null ? utilPct - prev(utilHist)! : null;

  return (
    <div className="flex flex-wrap gap-3">
      <KpiCard
        icon={<Activity className="w-4 h-4 text-rose-400" />}
        label="Open Incidents"
        value={String(open)}
        delta={dOpen}
        sub={
          <>
            <Sparkline values={openHist} stroke="#fb7185" width={72} height={18} />
            <span className="text-[10px] font-mono text-slate-500">
              of {incidents.length} total
              {open > 5 && <span className="text-rose-400"> · surge</span>}
            </span>
          </>
        }
        accent="text-rose-400"
      />
      <KpiCard
        icon={<Layers className="w-4 h-4 text-indigo-400" />}
        label="Decisions Emitted"
        value={String(decisions.length)}
        delta={dDec}
        sub={
          <>
            <Sparkline values={decisionHist} stroke="#818cf8" width={72} height={18} />
            <span className="text-[10px] font-mono text-slate-500">
              {state?.laya_mode ? state.laya_mode.toUpperCase() : '—'}
            </span>
          </>
        }
        accent="text-indigo-400"
      />
      <KpiCard
        icon={<Timer className="w-4 h-4 text-teal-400" />}
        label="Avg Laya Latency"
        value={lastLatency === null ? '—' : `${Math.round(lastLatency)} ms`}
        sub={
          <>
            <Sparkline values={latencies} />
            {lastLatency != null && lastLatency > 300 && (
              <span className="text-[10px] font-mono text-amber-400">· above 300 ms target</span>
            )}
          </>
        }
        accent="text-teal-400"
      />
      <KpiCard
        icon={<Gauge className="w-4 h-4 text-amber-400" />}
        label="Fleet Deployed"
        value={`${utilPct}%`}
        delta={dUtil}
        sub={
          <>
            <Sparkline values={utilHist} stroke="#fbbf24" width={72} height={18} />
            <span className="text-[10px] font-mono text-slate-500">
              {busy}/{resources.length || 0} units
              {utilPct >= 90 && <span className="text-amber-400"> · near max</span>}
            </span>
          </>
        }
        accent="text-amber-400"
      />
    </div>
  );
};

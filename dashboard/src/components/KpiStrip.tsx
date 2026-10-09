import type React from 'react';
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
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: React.ReactNode;
  accent: string;
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
          </div>
        </div>
      </div>
      {sub}
    </div>
  );
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
  const busy = resources.filter((r) => r.status !== 'available').length;
  const utilPct = Math.round((busy / total) * 100);
  const latencies = latencySeries.map((p) => p.v);
  const lastLatency = latencies.length > 0 ? latencies[latencies.length - 1] : null;

  return (
    <div className="flex flex-wrap gap-3">
      <KpiCard
        icon={<Activity className="w-4 h-4 text-rose-400" />}
        label="Open Incidents"
        value={String(open)}
        sub={
          <span className="text-[10px] font-mono text-slate-500">
            of {incidents.length} total
          </span>
        }
        accent="text-rose-400"
      />
      <KpiCard
        icon={<Layers className="w-4 h-4 text-indigo-400" />}
        label="Decisions Emitted"
        value={String(decisions.length)}
        sub={
          <span className="text-[10px] font-mono text-slate-500">
            {state?.laya_mode ? state.laya_mode.toUpperCase() : '—'}
          </span>
        }
        accent="text-indigo-400"
      />
      <KpiCard
        icon={<Timer className="w-4 h-4 text-teal-400" />}
        label="Avg Laya Latency"
        value={lastLatency === null ? '—' : `${Math.round(lastLatency)} ms`}
        sub={<Sparkline values={latencies} />}
        accent="text-teal-400"
      />
      <KpiCard
        icon={<Gauge className="w-4 h-4 text-amber-400" />}
        label="Fleet Deployed"
        value={`${utilPct}%`}
        sub={
          <span className="text-[10px] font-mono text-slate-500">
            {busy}/{resources.length || 0} units
          </span>
        }
        accent="text-amber-400"
      />
    </div>
  );
};

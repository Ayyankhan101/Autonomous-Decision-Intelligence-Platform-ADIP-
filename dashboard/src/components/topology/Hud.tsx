import { useState } from 'react';
import {
  Activity,
  Cpu,
  Gauge,
  ScrollText,
  OctagonPause,
  Play,
  Radio,
  ShieldAlert,
  X,
} from 'lucide-react';
import { useTopologyStore } from '../../stores/topologyStore';
import { api } from '../../services/api';
import type { ImpactPreviewResponse } from '../../types/api';

const STATUS_DOT: Record<string, string> = {
  available: 'bg-emerald-400',
  assigned: 'bg-cyan-400',
  busy: 'bg-amber-400',
  offline: 'bg-slate-500',
};

const STATUS_LABEL: Record<string, string> = {
  available: 'IDLE',
  assigned: 'ASSIGNED',
  busy: 'PROCESSING',
  offline: 'OFFLINE',
};

const LEVEL_COLOR: Record<string, string> = {
  ok: 'text-emerald-400',
  info: 'text-cyan-300',
  warn: 'text-amber-400',
  error: 'text-rose-400',
};

function Pane({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`bg-slate-900/80 backdrop-blur-md border border-cyan-500/30 rounded-lg shadow-[0_0_20px_rgba(34,211,238,0.08)] ${className}`}
    >
      {children}
    </div>
  );
}

function HudHeader() {
  const fps = useTopologyStore((s) => s.fps);
  const computeLoad = useTopologyStore((s) => s.computeLoad);
  const runtimeMode = useTopologyStore((s) => s.runtimeMode);
  const feedMode = useTopologyStore((s) => s.feedMode);
  const simulatedTime = useTopologyStore((s) => s.simulatedTime);
  const running = useTopologyStore((s) => s.running);

  const clock = simulatedTime
    ? `${simulatedTime.slice(11, 19)}${feedMode === 'live' ? ' PKT' : ''}`
    : '--:--:--';

  return (
    <>
      <Pane className="absolute top-3 left-3 px-4 py-2.5 z-10">
        <div className="flex items-center gap-2 text-[11px] font-mono tracking-widest text-cyan-300">
          <Radio className="w-3.5 h-3.5" />
          ADIP CORE STATUS
        </div>
        <div className="mt-1 text-[10px] font-mono text-slate-400 space-y-0.5">
          <div>
            Runtime: <span className="text-slate-200">laya-adapter ({runtimeMode})</span>
          </div>
          <div className="flex items-center gap-1.5">
            Status:
            <span
              className={`inline-flex items-center gap-1 px-1.5 py-px rounded ${
                running ? 'bg-cyan-500/15 text-cyan-300' : 'bg-slate-700/50 text-slate-400'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${running ? 'bg-cyan-400 animate-pulse' : 'bg-slate-500'}`}
              />
              {running ? 'Operational' : 'Paused'}
            </span>
          </div>
          {feedMode === 'live' && (
            <div className="text-[9px] text-cyan-400/80">LIVE FEED MODE · real external feeds</div>
          )}
        </div>
      </Pane>

      <Pane className="absolute top-3 right-3 px-4 py-2.5 z-10 text-right">
        <div className="text-sm font-mono text-cyan-300 tabular-nums tracking-wider">{clock}</div>
        <div className="mt-1 text-[10px] font-mono text-slate-400 space-y-0.5">
          <div className="flex items-center justify-end gap-1.5">
            <Activity className="w-3 h-3" /> {fps} FPS
          </div>
          <div className="flex items-center justify-end gap-1.5">
            <Gauge className="w-3 h-3" /> {computeLoad}% UTILISATION (est.)
          </div>
          <div className="flex items-center justify-end gap-1.5 text-[9px] text-slate-500">
            <Cpu className="w-3 h-3" /> agent telemetry (derived)
          </div>
        </div>
      </Pane>
    </>
  );
}

function AgentMatrix() {
  const agents = useTopologyStore((s) => s.agents);
  const selectedAgentId = useTopologyStore((s) => s.selectedAgentId);
  const selectAgent = useTopologyStore((s) => s.selectAgent);

  const counts = agents.reduce(
    (acc, a) => {
      acc[a.status] += 1;
      return acc;
    },
    { available: 0, assigned: 0, busy: 0, offline: 0 } as Record<string, number>,
  );

  return (
    <Pane className="absolute top-20 left-3 w-56 max-h-[calc(100%-11rem)] overflow-y-auto z-10">
      <div className="px-3 py-2 border-b border-cyan-500/20">
        <div className="text-[10px] font-mono tracking-widest text-cyan-300">
          AGENT MATRIX ({agents.length})
        </div>
        <div className="mt-1 flex flex-wrap gap-1 text-[8px] font-mono">
          <span className="px-1 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            {counts.available} idle
          </span>
          <span className="px-1 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
            {counts.assigned} assigned
          </span>
          <span className="px-1 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
            {counts.busy} busy
          </span>
          <span className="px-1 rounded bg-slate-600/20 text-slate-400 border border-slate-600/40">
            {counts.offline} off
          </span>
        </div>
      </div>
      <ul className="divide-y divide-slate-800/60">
        {agents.map((a) => (
          <li key={a.id}>
            <button
              type="button"
              onClick={() => selectAgent(a.id === selectedAgentId ? null : a.id)}
              className={`w-full text-left px-3 py-1.5 text-[10px] font-mono hover:bg-cyan-500/10 ${
                a.id === selectedAgentId ? 'bg-cyan-500/15' : ''
              }`}
            >
              <div className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[a.status]}`} />
                <span className="text-slate-200 truncate">{a.id}</span>
                <span className="ml-auto text-slate-500">{a.type.split('_')[0]}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[9px]">
                <span className="text-slate-500">{STATUS_LABEL[a.status]}</span>
                <span className="text-slate-400">
                  {a.decisionConfidence != null ? `${a.decisionConfidence}% conf` : '—'}
                </span>
                <span className="ml-auto w-10 h-1 bg-slate-800 rounded overflow-hidden">
                  <span
                    className="block h-full bg-cyan-500/70"
                    style={{ width: `${a.processingLoad}%` }}
                  />
                </span>
              </div>
            </button>
          </li>
        ))}
        {agents.length === 0 && (
          <li className="px-3 py-4 text-[10px] font-mono text-slate-500">AWAITING TELEMETRY</li>
        )}
      </ul>
    </Pane>
  );
}

function TelemetryPanel() {
  const selectedAgentId = useTopologyStore((s) => s.selectedAgentId);
  const agents = useTopologyStore((s) => s.agents);
  const selectAgent = useTopologyStore((s) => s.selectAgent);
  const pushLog = useTopologyStore((s) => s.pushLog);
  const [overrideState, setOverrideState] = useState<
    | { phase: 'idle' }
    | { phase: 'loading' }
    | { phase: 'confirm'; preview: ImpactPreviewResponse }
    | { phase: 'done'; tier: string }
    | { phase: 'error'; message: string }
  >({ phase: 'idle' });

  const agent = agents.find((a) => a.id === selectedAgentId) ?? null;
  if (!agent) return null;

  const handleOverride = async () => {
    if (!agent.lastDecisionId) return;
    setOverrideState({ phase: 'loading' });
    try {
      const preview = await api.impactPreview({
        decision_id: agent.lastDecisionId,
        override_type: 'OVERRIDE_AUTOMATION_HOLD',
      });
      setOverrideState({ phase: 'confirm', preview });
    } catch (e) {
      setOverrideState({
        phase: 'error',
        message: e instanceof Error ? e.message : 'impact preview failed',
      });
    }
  };

  const confirmOverride = async () => {
    if (!agent.lastDecisionId || overrideState.phase !== 'confirm') return;
    const { preview } = overrideState;
    try {
      await api.applyOverride({
        operator_id: 'topology-hud',
        decision_id: agent.lastDecisionId,
        override_type: 'OVERRIDE_AUTOMATION_HOLD',
        reason: `Topology HUD operator override (${preview.tier} tier)`,
        reason_code: 'EXTERNAL_CONTEXT',
        impact_ack: preview.requires_ack,
        break_glass: preview.requires_break_glass,
      });
      pushLog({
        key: `local:ov:${agent.lastDecisionId}:${Date.now()}`,
        ts: new Date().toISOString().slice(11, 19),
        level: 'warn',
        text: `OVERRIDE applied · ${agent.lastDecisionId} · operator topology-hud · tier ${preview.tier}`,
      });
      setOverrideState({ phase: 'done', tier: preview.tier });
    } catch (e) {
      setOverrideState({
        phase: 'error',
        message: e instanceof Error ? e.message : 'override failed',
      });
    }
  };

  return (
    <Pane className="absolute top-20 right-3 w-64 z-20 overflow-hidden max-h-[calc(100%-10.5rem)] flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-cyan-500/20">
        <span className="text-[10px] font-mono tracking-widest text-cyan-300">NODE TELEMETRY</span>
        <button
          type="button"
          onClick={() => {
            selectAgent(null);
            setOverrideState({ phase: 'idle' });
          }}
          className="text-slate-500 hover:text-slate-200"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="p-3 text-[10px] font-mono space-y-1.5 overflow-y-auto">
        <div className="text-slate-200 text-xs">{agent.id}</div>
        <div className="text-slate-500">
          {agent.type} · {agent.zone} zone
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[agent.status]}`} />
          <span className="text-slate-300">{STATUS_LABEL[agent.status]}</span>
        </div>
        <div className="text-slate-400">
          Task: <span className="text-slate-200">{agent.currentTask ?? '—'}</span>
        </div>
        <div className="text-slate-400">
          
        </div>
        <div className="text-slate-400">
          Confidence:{' '}
          <span className="text-cyan-300">
            {agent.decisionConfidence != null ? `${agent.decisionConfidence}%` : '—'}
          </span>
        </div>
        {agent.lat != null && agent.lon != null && (
          <div className="text-slate-500 text-[9px]">
            GPS {agent.lat.toFixed(4)}, {agent.lon.toFixed(4)}
          </div>
        )}

        <div className="pt-2 border-t border-slate-800 space-y-1.5">
          {overrideState.phase === 'idle' && (
            <button
              type="button"
              disabled={!agent.lastDecisionId}
              onClick={handleOverride}
              className="w-full px-2 py-1.5 rounded bg-amber-500/15 border border-amber-500/40 text-amber-300 hover:bg-amber-500/25 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              OVERRIDE DECISION
            </button>
          )}
          {overrideState.phase === 'loading' && (
            <div className="text-slate-500 text-center py-1.5">checking impact tier…</div>
          )}
          {overrideState.phase === 'confirm' && (
            <div className="space-y-1.5">
              <div
                className={`text-[9px] px-2 py-1 rounded border ${
                  overrideState.preview.tier === 'BREAK_GLASS'
                    ? 'bg-rose-500/15 border-rose-500/40 text-rose-300'
                    : overrideState.preview.tier === 'HIGH'
                      ? 'bg-amber-500/15 border-amber-500/40 text-amber-300'
                      : 'bg-slate-700/40 border-slate-600 text-slate-300'
                }`}
              >
                TIER {overrideState.preview.tier} — {overrideState.preview.warning}
              </div>
              <button
                type="button"
                onClick={confirmOverride}
                className="w-full px-2 py-1.5 rounded bg-rose-500/20 border border-rose-500/50 text-rose-200 hover:bg-rose-500/30"
              >
                CONFIRM OVERRIDE
              </button>
              <button
                type="button"
                onClick={() => setOverrideState({ phase: 'idle' })}
                className="w-full px-2 py-1 rounded text-slate-500 hover:text-slate-300"
              >
                cancel
              </button>
            </div>
          )}
          {overrideState.phase === 'done' && (
            <div className="text-[9px] text-emerald-400 px-2 py-1">
              OVERRIDE APPLIED ({overrideState.tier}) — refresh feeds to see new state
            </div>
          )}
          {overrideState.phase === 'error' && (
            <div className="text-[9px] text-rose-400 px-2 py-1 break-words">
              {overrideState.message}
            </div>
          )}

          <button
            type="button"
            disabled
            title="No CPS teardown API — Rescue 1122 integration pending. Visual-only flag."
            className="w-full px-2 py-1.5 rounded bg-slate-800/60 border border-slate-700 text-slate-500 cursor-not-allowed flex items-center justify-center gap-1.5"
          >
            <OctagonPause className="w-3 h-3" />
            TERMINATE NODE (no backend API)
          </button>
        </div>
      </div>
    </Pane>
  );
}

function BottomTicker({ onRefresh }: { onRefresh: () => void }) {
  const logs = useTopologyStore((s) => s.logs);
  const simSpeed = useTopologyStore((s) => s.simSpeed);
  const visualPaused = useTopologyStore((s) => s.visualPaused);
  const setSimSpeed = useTopologyStore((s) => s.setSimSpeed);
  const setVisualPaused = useTopologyStore((s) => s.setVisualPaused);
  const flashAnomaly = useTopologyStore((s) => s.flashAnomaly);
  const pushLog = useTopologyStore((s) => s.pushLog);
  const [injecting, setInjecting] = useState(false);
  const [injectError, setInjectError] = useState<string | null>(null);

  const handleInject = async () => {
    setInjecting(true);
    setInjectError(null);
    try {
      const res = await api.injectBadData({ mode: 'adversarial_notes' });
      if (res.incident_id) flashAnomaly(res.incident_id);
      pushLog({
        key: `local:inj:${Date.now()}`,
        ts: new Date().toISOString().slice(11, 19),
        level: 'error',
        text: `malicious anomaly injected · adversarial_notes · ${res.incident_id ?? 'pending incident'} · ${res.decision_ids.length} decision(s) queued`,
      });
      onRefresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'injection failed';
      setInjectError(msg);
      pushLog({
        key: `local:inj-err:${Date.now()}`,
        ts: new Date().toISOString().slice(11, 19),
        level: 'error',
        text: `anomaly injection rejected — ${msg}`,
      });
    } finally {
      setInjecting(false);
    }
  };

  const speedBtn = (label: string, value: number, active: boolean) => (
    <button
      key={label}
      type="button"
      onClick={() => {
        setSimSpeed(value);
        setVisualPaused(false);
      }}
      className={`px-1.5 py-0.5 rounded text-[9px] font-mono border ${
        active && !visualPaused
          ? 'bg-cyan-500/20 border-cyan-400/50 text-cyan-300'
          : 'border-slate-700 text-slate-500 hover:text-slate-300'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="absolute bottom-3 left-3 right-3 z-10 flex gap-3 items-end">
      <Pane className="flex-1 min-w-0 h-24 overflow-hidden flex flex-col">
        <div className="px-3 py-1 border-b border-cyan-500/20 text-[9px] font-mono tracking-widest text-cyan-300 flex items-center gap-1.5">
          <ScrollText className="w-3 h-3" />
          EVENT LOG (live backend tail)
        </div>
        <ul className="flex-1 overflow-y-auto px-3 py-1 space-y-0.5 font-mono text-[9px]">
          {logs.map((l) => (
            <li key={l.key} className="flex gap-2">
              <span className="text-slate-600 tabular-nums">{l.ts}</span>
              <span className={LEVEL_COLOR[l.level] ?? 'text-slate-400'}>{l.text}</span>
            </li>
          ))}
          {logs.length === 0 && <li className="text-slate-600">no events yet</li>}
        </ul>
      </Pane>

      <Pane className="px-3 py-2 flex flex-col gap-1.5">
        <div className="flex items-center gap-1">
          <span className="text-[9px] font-mono text-slate-500 mr-1">SIM SPEED</span>
          {speedBtn('1x', 1, simSpeed === 1)}
          {speedBtn('2x', 2, simSpeed === 2)}
          {speedBtn('4x', 4, simSpeed === 4)}
          <button
            type="button"
            onClick={() => setVisualPaused(!visualPaused)}
            className={`px-1.5 py-0.5 rounded text-[9px] font-mono border flex items-center gap-1 ${
              visualPaused
                ? 'bg-amber-500/20 border-amber-400/50 text-amber-300'
                : 'border-slate-700 text-slate-500 hover:text-slate-300'
            }`}
            title="Pauses local visual jitter only — backend sim pause lives in Command tab"
          >
            {visualPaused ? <Play className="w-2.5 h-2.5" /> : <OctagonPause className="w-2.5 h-2.5" />}
            {visualPaused ? 'PAUSED' : 'PAUSE'}
          </button>
        </div>
        <div className="text-[8px] text-slate-600 font-mono -mt-0.5">
          visual sim only — backend control in Command tab
        </div>
        <button
          type="button"
          onClick={handleInject}
          disabled={injecting}
          className="px-2 py-1 rounded bg-rose-500/15 border border-rose-500/40 text-rose-300 hover:bg-rose-500/25 disabled:opacity-50 text-[10px] font-mono tracking-wider flex items-center gap-1.5"
        >
          <ShieldAlert className="w-3 h-3" />
          {injecting ? 'INJECTING…' : 'INJECT MALICIOUS ANOMALY'}
        </button>
        {injectError && (
          <div className="text-[8px] text-rose-400 max-w-48 break-words">{injectError}</div>
        )}
      </Pane>
    </div>
  );
}

export function Hud({ onRefresh }: { onRefresh: () => void }) {
  return (
    <>
      <HudHeader />
      <AgentMatrix />
      <TelemetryPanel />
      <BottomTicker onRefresh={onRefresh} />
    </>
  );
}

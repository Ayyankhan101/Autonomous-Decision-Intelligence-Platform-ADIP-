import type React from 'react';
import { useState } from 'react';
import { Scale, Leaf, Timer, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import type { PolicyPosition } from '../types/api';

interface PolicySandboxProps {
  position: PolicyPosition;
  objectiveWeights?: Record<string, number>;
  onRefresh: () => void;
}

const POSITIONS: {
  key: PolicyPosition;
  label: string;
  description: string;
  icon: React.ReactNode;
  tone: string;
  weights: Record<string, number>;
}[] = [
  {
    key: 'RESPONSE_TIME',
    label: 'Response Time',
    description: 'Fastest arrival — baseline local-first allocation',
    icon: <Timer className="w-3.5 h-3.5" />,
    tone: 'sky',
    weights: { response_time: 1.0, equity: 0.0, emissions: 0.0 },
  },
  {
    key: 'EQUITY',
    label: 'Equity',
    description: 'Underserved zones (north/west) get +1 priority step',
    icon: <Scale className="w-3.5 h-3.5" />,
    tone: 'violet',
    weights: { response_time: 0.0, equity: 1.0, emissions: 0.0 },
  },
  {
    key: 'ECO',
    label: 'Eco',
    description: 'Electric-first — highest eco_score candidate wins',
    icon: <Leaf className="w-3.5 h-3.5" />,
    tone: 'emerald',
    weights: { response_time: 0.0, equity: 0.0, emissions: 1.0 },
  },
];

const TONE_BUTTON_ACTIVE: Record<string, string> = {
  sky: 'border-sky-400 bg-sky-950 text-sky-100 shadow-[0_0_10px_rgba(56,189,248,0.25)]',
  violet: 'border-violet-400 bg-violet-950 text-violet-100 shadow-[0_0_10px_rgba(167,139,250,0.25)]',
  emerald:
    'border-emerald-400 bg-emerald-950 text-emerald-100 shadow-[0_0_10px_rgba(52,211,153,0.25)]',
};

const TONE_BUTTON_IDLE =
  'border-slate-700 bg-slate-950 text-slate-400 hover:border-slate-500 hover:text-slate-200';

export const PolicySandbox: React.FC<PolicySandboxProps> = ({
  position,
  objectiveWeights,
  onRefresh,
}) => {
  // pending = operator's unstaged pick; null = follow live position (no effect ref needed)
  const [pending, setPending] = useState<PolicyPosition | null>(null);
  const [reoptimise, setReoptimise] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const target = pending ?? position;
  const activeDef = POSITIONS.find((p) => p.key === target) ?? POSITIONS[0];
  const weights = objectiveWeights ?? activeDef.weights;

  const showToast = (text: string, type: 'success' | 'error' = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  const handleApply = async () => {
    setIsSubmitting(true);
    try {
      const res = await api.policyPosition(target, reoptimise);
      const affected = res.affected_decisions.length;
      showToast(
        res.previous_position === res.position
          ? `Already at ${res.position}`
          : `${res.previous_position} → ${res.position}: ${affected} pending decision${
              affected === 1 ? '' : 's'
            } would change, ${res.reoptimised} re-optimised`,
        res.previous_position === res.position ? 'error' : 'success',
      );
      setPending(null);
      onRefresh();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-md flex flex-col gap-3">
      {message && (
        <div
          className={`p-2.5 rounded-lg text-xs font-mono border flex items-center justify-between transition-all ${
            message.type === 'success'
              ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/50'
              : 'bg-red-950/80 text-red-300 border-red-500/50'
          }`}
        >
          <span>{message.text}</span>
          <button onClick={() => setMessage(null)} className="text-slate-400 hover:text-white">
            ×
          </button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse" />
          <span>Policy Sandbox</span>
        </h3>
        <span className="text-[10px] font-mono text-slate-500">
          Live: <span className="text-teal-300">{position}</span>
        </span>
      </div>

      <p className="text-[10px] text-slate-500 leading-relaxed">
        Pre-registered objective weights. Switch applies to NEW decisions only unless you
        re-optimise active incidents.
      </p>

      <div className="flex flex-col gap-1.5">
        {POSITIONS.map((p) => {
          const isActive = target === p.key;
          const isLive = position === p.key;
          return (
            <button
              key={p.key}
              onClick={() => setPending(p.key === position ? null : p.key)}
              disabled={isSubmitting}
              title={p.description}
              className={`w-full text-left px-2.5 py-2 rounded-lg border text-xs transition-all flex items-center justify-between gap-2 ${
                isActive ? TONE_BUTTON_ACTIVE[p.tone] : TONE_BUTTON_IDLE
              }`}
            >
              <span className="flex items-center gap-1.5 font-semibold">
                {p.icon}
                <span>{p.label}</span>
              </span>
              <span className="text-[9px] font-mono uppercase tracking-wide opacity-80">
                {isLive ? 'live' : isActive ? 'selected' : ''}
              </span>
            </button>
          );
        })}
      </div>

      <div className="border-t border-slate-800/80 pt-2.5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
            Objective weights
          </span>
          <span className="text-[10px] font-mono text-slate-400">
            rt {weights.response_time?.toFixed(1) ?? '0.0'} · eq{' '}
            {weights.equity?.toFixed(1) ?? '0.0'} · em{' '}
            {weights.emissions?.toFixed(1) ?? '0.0'}
          </span>
        </div>

        <label className="flex items-center gap-2 text-[11px] text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={reoptimise}
            onChange={(e) => setReoptimise(e.target.checked)}
            disabled={isSubmitting}
            className="rounded bg-slate-950 border-slate-700 text-teal-600 focus:ring-0"
          />
          <span>
            Re-optimise active incidents{' '}
            <span className="text-slate-500">(new decisions + rewrite pending allocations)</span>
          </span>
        </label>

        <button
          onClick={handleApply}
          disabled={isSubmitting || pending === null}
          className="w-full py-1.5 rounded-lg text-xs font-semibold bg-teal-700 hover:bg-teal-600 disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed text-white flex items-center justify-center gap-1.5 shadow-sm transition-all"
          title={
            pending === null
              ? 'Select a different position to switch'
              : `Switch to ${target}`
          }
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isSubmitting ? 'animate-spin' : ''}`} />
          <span>
            {pending === null
              ? `Position: ${position}`
              : `Switch ${position} → ${target}`}
          </span>
        </button>
      </div>
    </div>
  );
};

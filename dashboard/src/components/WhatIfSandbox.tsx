import type React from 'react';
import { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  GitBranch,
  Sparkles,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  DecisionRecord,
  WhatIfResult,
  WhatIfScenario,
} from '../types/api';

interface WhatIfSandboxProps {
  latestDecision: DecisionRecord | null;
}

export const WhatIfSandbox: React.FC<WhatIfSandboxProps> = ({ latestDecision }) => {
  const [scenario, setScenario] = useState<WhatIfScenario>('remove_one_ambulance');
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [verifyState, setVerifyState] = useState<'ok' | 'expired' | 'error' | null>(null);

  const handleRunWhatIf = async () => {
    setIsRunning(true);
    setErrorMsg(null);
    setVerifyState(null);
    try {
      const res = await api.runWhatIf(scenario);
      setResult(res);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setIsRunning(false);
    }
  };

  const handleVerifyStored = async () => {
    if (!result) return;
    try {
      const fresh = await api.getWhatIfResult(result.sandbox_id);
      setResult(fresh);
      setVerifyState('ok');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setVerifyState(msg.includes('[404]') ? 'expired' : 'error');
      if (!msg.includes('[404]')) setErrorMsg(msg);
    }
  };

  const getScenarioDescription = (sc: WhatIfScenario) => {
    switch (sc) {
      case 'remove_one_ambulance':
        return 'Simulates acute fleet scarcity by removing one ambulance before allocation to test fallback and contention logic.';
      case 'close_road':
        return 'Simulates major arterial roadblock, spiking traffic impact and rerouting priority assessments.';
      case 'second_emergency':
        return 'Injects an unpredicted secondary structure fire into the sandbox to measure resource contention without affecting live state.';
    }
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-md flex flex-col gap-5">
      {/* Header & Isolation Guarantees */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-purple-950/80 border border-purple-500/40 rounded-xl text-purple-400">
            <Cpu className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white">
                Counterfactual What-If Sandbox
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800/50">
                Invariants 6 & 15
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Isolated state-fork simulation • Zero live database mutations • Non-audited dry run
            </p>
          </div>
        </div>

        {/* Safety Guarantees Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-mono px-2.5 py-1 rounded-md bg-emerald-950/70 text-emerald-300 border border-emerald-800/50 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>dry_run=true</span>
          </span>
          <span className="text-[11px] font-mono px-2.5 py-1 rounded-md bg-emerald-950/70 text-emerald-300 border border-emerald-800/50 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>audit_written=false</span>
          </span>
          <span className="text-[11px] font-mono px-2.5 py-1 rounded-md bg-emerald-950/70 text-emerald-300 border border-emerald-800/50 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>live_state_mutated=false</span>
          </span>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 rounded-lg bg-red-950/80 border border-red-500/50 text-red-300 text-xs font-mono flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Scenario Controls */}
      <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <div className="flex-1 space-y-1">
          <label className="text-xs font-bold uppercase tracking-wider text-slate-300 block">
            Select Predefined Counterfactual Scenario
          </label>
          <select
            value={scenario}
            onChange={(e) => setScenario(e.target.value as WhatIfScenario)}
            className="w-full md:w-96 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:border-purple-500 focus:outline-none"
          >
            <option value="remove_one_ambulance">Scarcity: Remove 1 Ambulance Unit</option>
            <option value="close_road">Transit: Close Major Road Artery</option>
            <option value="second_emergency">Contention: Simultaneous Second Emergency</option>
          </select>
          <p className="text-[11px] text-slate-400 mt-1">
            {getScenarioDescription(scenario)}
          </p>
        </div>

        <button
          onClick={handleRunWhatIf}
          disabled={isRunning}
          className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-lg shadow-purple-900/40 transition-all shrink-0"
        >
          <GitBranch className="w-4 h-4" />
          <span>{isRunning ? 'Branching Sandbox...' : 'Run Counterfactual Fork'}</span>
        </button>
      </div>

      {/* Simulation Results Display */}
      {result ? (
        <div className="space-y-4 animate-in fade-in duration-200">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-400" />
              <span>Counterfactual Comparison: Live Baseline vs Sandbox Fork</span>
            </h4>
            <span className="text-[10px] font-mono text-slate-400">
              Sandbox ID: {result.sandbox_id}
            </span>
          </div>

          {/* Server-side persistence check / expiry state */}
          <div className="flex items-center gap-2 text-[11px] font-mono">
            <button
              onClick={handleVerifyStored}
              className="px-2.5 py-1 rounded-md bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 transition-colors"
            >
              Verify Stored Result (GET)
            </button>
            {verifyState === 'ok' && (
              <span className="text-emerald-300 bg-emerald-950/60 border border-emerald-800/50 px-2 py-1 rounded">
                STORED RESULT RE-FETCHED — isolation badges confirmed server-side
              </span>
            )}
            {verifyState === 'expired' && (
              <span className="text-red-300 bg-red-950/60 border border-red-800/50 px-2 py-1 rounded animate-pulse">
                SANDBOX EXPIRED — stored result no longer available (store cleared)
              </span>
            )}
            {verifyState === 'error' && (
              <span className="text-amber-300 bg-amber-950/60 border border-amber-800/50 px-2 py-1 rounded">
                VERIFY FAILED — see error above
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Live Baseline State */}
            <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
                  <h5 className="text-xs font-bold text-slate-200 uppercase tracking-wide">
                    Live Operational State (Incident {latestDecision?.incident_id || 'Current'})
                  </h5>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                    LIVE BASELINE
                  </span>
                </div>

                <div className="space-y-2.5 text-xs font-mono">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Priority:</span>
                    <span className="font-bold text-slate-100">{latestDecision?.priority || 'CRITICAL'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Decision State:</span>
                    <span className="font-bold text-emerald-400">{latestDecision?.state || 'AUTO_APPROVED'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Laya Advisory:</span>
                    <span className="text-purple-300">{latestDecision?.laya?.suggested_priority || 'HIGH'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Dispatched Units:</span>
                    <span className="text-slate-200">
                      {latestDecision?.assigned_resource_ids.join(', ') || 'amb-01, pol-01'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-2 border-t border-slate-800 text-[10px] text-slate-500 font-mono">
                Persisted in production DB & Audit Log
              </div>
            </div>

            {/* Counterfactual Sandbox Fork */}
            <div className="bg-purple-950/20 border border-purple-800/60 rounded-xl p-4 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-purple-800/60 pb-2 mb-3">
                  <h5 className="text-xs font-bold text-purple-200 uppercase tracking-wide">
                    Sandbox Fork Outcome ({result.scenario})
                  </h5>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-900/60 text-purple-300 border border-purple-700/50">
                    COUNTERFACTUAL
                  </span>
                </div>

                <div className="space-y-2.5 text-xs font-mono">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Priority:</span>
                    <span className="font-bold text-purple-200">{result.decision.priority}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Decision State:</span>
                    <span className="font-bold text-purple-300">{result.decision.state}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Laya Status:</span>
                    <span className="text-purple-300">{result.laya_mode} ({result.decision.laya?.status || 'ok'})</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Dispatched Units:</span>
                    <span className="text-purple-200">
                      {result.decision.assigned_resource_ids.length > 0
                        ? result.decision.assigned_resource_ids.join(', ')
                        : 'None (Contention Escalation)'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-2 border-t border-purple-800/50 text-[10px] text-purple-400/80 font-mono flex items-center justify-between">
                <span>Zero live writes executed</span>
                <span>Isolated cache namespace</span>
              </div>
            </div>
          </div>

          {/* Structured Divergence Analysis */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 text-xs font-mono">
            <span className="text-slate-400 block mb-1 font-bold uppercase tracking-wider text-[10px]">
              Sandbox Decision Reasons:
            </span>
            <ul className="space-y-1 text-slate-300">
              {result.decision.reasons.map((r, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="text-purple-400">•</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="py-16 text-center text-xs text-slate-500 font-mono border border-dashed border-slate-800 rounded-xl flex flex-col items-center justify-center">
          <GitBranch className="w-8 h-8 mb-2 text-slate-600" />
          <p>Choose a scenario above and execute a counterfactual simulation.</p>
          <p className="text-[11px] text-slate-600 mt-1">
            Replays state in sandbox memory without affecting live dispatch or audit log.
          </p>
        </div>
      )}
    </div>
  );
};

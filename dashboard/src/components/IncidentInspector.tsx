import type React from 'react';
import { useState } from 'react';
import {
  Brain,
  CheckCircle2,
  Cpu,
  FileCheck,
  HelpCircle,
  Lock,
  Scale,
  ShieldAlert,
  UserCheck,
} from 'lucide-react';
import type {
  DecisionRecord,
  DecisionState,
  IncidentRecord,
  Priority,
} from '../types/api';

interface IncidentInspectorProps {
  incident: IncidentRecord | null;
  decision: DecisionRecord | null;
  onOpenOverrideModal: () => void;
}

export const IncidentInspector: React.FC<IncidentInspectorProps> = ({
  incident,
  decision,
  onOpenOverrideModal,
}) => {
  const [advisoryVisible, setAdvisoryVisible] = useState(true);

  if (!incident) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-8 text-center text-slate-500 font-mono flex flex-col items-center justify-center min-h-[400px]">
        <HelpCircle className="w-10 h-10 mb-2 text-slate-600" />
        <p className="text-sm">Select an incident from the map or list to inspect decision lineage.</p>
      </div>
    );
  }

  const laya = decision?.laya;
  const signals = decision?.signals;
  const override = decision?.override;

  const isDiverged =
    laya &&
    laya.suggested_priority &&
    decision &&
    decision.priority &&
    laya.suggested_priority !== decision.priority;

  const getPriorityColor = (p?: Priority | string | null) => {
    switch (p) {
      case 'CRITICAL':
        return 'text-red-400 bg-red-950/60 border-red-500/50';
      case 'HIGH':
        return 'text-amber-400 bg-amber-950/60 border-amber-500/50';
      case 'MEDIUM':
        return 'text-yellow-400 bg-yellow-950/60 border-yellow-500/50';
      case 'LOW':
        return 'text-blue-400 bg-blue-950/60 border-blue-500/50';
      default:
        return 'text-slate-400 bg-slate-950/60 border-slate-700';
    }
  };

  const getStateColor = (s?: DecisionState | string) => {
    switch (s) {
      case 'AUTO_APPROVED':
        return 'text-emerald-400 bg-emerald-950/60 border-emerald-500/50';
      case 'HOLD_FOR_HUMAN':
        return 'text-purple-400 bg-purple-950/60 border-purple-500/50';
      case 'CONTENTION_ESCALATION':
        return 'text-rose-400 bg-rose-950/60 border-rose-500/50';
      case 'OVERRIDE_ACTIVE':
        return 'text-cyan-400 bg-cyan-950/60 border-cyan-500/50';
      case 'MODEL_DEGRADED':
        return 'text-orange-400 bg-orange-950/60 border-orange-500/50';
      case 'REJECTED_INPUT':
        return 'text-slate-400 bg-slate-950/60 border-slate-700';
      default:
        return 'text-slate-400 bg-slate-950/60 border-slate-700';
    }
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-md flex flex-col gap-4">
      {/* Incident Header & Actions */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-bold font-mono text-white">
              {incident.incident_id}
            </span>
            <span className="px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700">
              {incident.incident_type.replace('_', ' ')}
            </span>
            <span className="px-2 py-0.5 rounded text-[11px] font-mono text-cyan-300 bg-cyan-950/50 border border-cyan-800/50">
              Zone: {incident.zone.toUpperCase()}
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[11px] font-mono border ${
                incident.validation_status === 'valid'
                  ? 'text-emerald-300 bg-emerald-950/50 border-emerald-800/50'
                  : incident.validation_status === 'soft_flagged'
                    ? 'text-amber-300 bg-amber-950/50 border-amber-800/50'
                    : 'text-red-300 bg-red-950/50 border-red-800/50'
              }`}
              title="Ingestion validation status (quality hint)"
            >
              DQ: {incident.validation_status.replace('_', ' ').toUpperCase()}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400 mt-1 font-mono">
            <span>First seen: {new Date(incident.first_seen_simulated).toLocaleTimeString()}</span>
            <span>•</span>
            <span>Reports: {incident.report_count}</span>
            <span>•</span>
            <span>Sources: {incident.source_ids.join(', ')}</span>
          </div>
        </div>

        {/* Human Override Trigger */}
        <div className="flex items-center gap-2">
          {decision && (
            <button
              onClick={onOpenOverrideModal}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1.5 transition-all shadow-md shadow-indigo-900/30"
            >
              <UserCheck className="w-4 h-4" />
              <span>Apply Human Override</span>
            </button>
          )}
        </div>
      </div>

      {/* Active Override Banner if present */}
      {override && (
        <div className="bg-cyan-950/40 border border-cyan-500/50 rounded-lg p-3 flex flex-col gap-1.5 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-cyan-300 font-semibold text-xs">
              <Lock className="w-4 h-4 text-cyan-400" />
              <span>ACTIVE HUMAN OVERRIDE IN EFFECT (Invariant 7)</span>
            </div>
            <span className="text-[10px] font-mono text-cyan-400">
              Op: {override.operator_id}
            </span>
          </div>
          <div className="text-xs text-slate-300">
            <strong className="text-cyan-200">Override Action:</strong> {override.override_type} •{' '}
            <strong className="text-cyan-200">Justification:</strong> &ldquo;{override.reason}&rdquo;
          </div>
          <div className="text-[11px] font-mono text-slate-400 flex items-center gap-2">
            <span>Original automated state: <strong className="text-slate-200">{override.previous_state}</strong> ({override.previous_priority})</span>
          </div>
        </div>
      )}

      {/* ML Triad Predictions Bar */}
      <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-indigo-400" />
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Independent Upstream ML Signals (Invariant 10)
            </h4>
          </div>
          <span className="text-[10px] text-slate-500 font-mono">
            Requires ≥2 independent signals for CRITICAL
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
          {/* Severity Model */}
          <div className="bg-slate-900/90 border border-slate-800/80 rounded-lg p-2.5 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-slate-300">Severity Model</span>
              <span className="text-[9px] font-mono text-slate-500">sev-gb-1.0.0</span>
            </div>
            <div className="my-1.5 flex items-baseline justify-between">
              <span className="text-sm font-bold font-mono text-slate-100">
                {signals?.severity.prediction || 'N/A'}
              </span>
              <span className="text-xs font-mono text-indigo-300 font-bold">
                {signals?.severity.confidence !== undefined && signals?.severity.confidence !== null
                  ? `${(signals.severity.confidence * 100).toFixed(1)}% conf`
                  : '--'}
              </span>
            </div>
            <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500"
                style={{ width: `${(signals?.severity.confidence || 0) * 100}%` }}
              />
            </div>
          </div>

          {/* Traffic Impact Model */}
          <div className="bg-slate-900/90 border border-slate-800/80 rounded-lg p-2.5 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-slate-300">Traffic Congestion</span>
              <span className="text-[9px] font-mono text-slate-500">traffic-gbr-1.0.0</span>
            </div>
            <div className="my-1.5 flex items-baseline justify-between">
              <span className="text-sm font-bold font-mono text-slate-100">
                {signals?.traffic.predicted_congestion_delta !== undefined &&
                signals?.traffic.predicted_congestion_delta !== null
                  ? `+${signals.traffic.predicted_congestion_delta.toFixed(1)}%`
                  : 'N/A'}
              </span>
              <span className="text-xs font-mono text-cyan-300 font-bold">
                {signals?.traffic.confidence !== undefined && signals?.traffic.confidence !== null
                  ? `${(signals.traffic.confidence * 100).toFixed(1)}% conf`
                  : '--'}
              </span>
            </div>
            <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
              <div
                className="h-full bg-cyan-500"
                style={{ width: `${(signals?.traffic.confidence || 0) * 100}%` }}
              />
            </div>
          </div>

          {/* Anomaly & Data Quality */}
          <div className="bg-slate-900/90 border border-slate-800/80 rounded-lg p-2.5 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-slate-300">Anomaly & Data Quality</span>
              <span className="text-[9px] font-mono text-slate-500">anom-ml-1.0.0</span>
            </div>
            <div className="my-1.5 flex items-baseline justify-between">
              <span className="text-sm font-bold font-mono text-slate-100">
                {signals?.data_quality.anomaly ? (
                  <span className="text-amber-400">ANOMALY DETECTED</span>
                ) : (
                  <span className="text-emerald-400">NORMAL DATA</span>
                )}
              </span>
              <span className="text-xs font-mono text-slate-300 font-bold">
                DQ: {((1 - (signals?.data_quality.data_quality_score || 0)) * 100).toFixed(0)}%
              </span>
            </div>
            <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
              <div
                className={`h-full ${
                  (signals?.data_quality.data_quality_score || 0) > 0.4 ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
                style={{
                  width: `${(1 - (signals?.data_quality.data_quality_score || 0)) * 100}%`,
                }}
              />
            </div>
          </div>
        </div>

        {signals?.data_quality.reasons && signals.data_quality.reasons.length > 0 && (
          <div className="mt-2 text-[11px] font-mono text-amber-300/90 bg-amber-950/30 p-1.5 rounded border border-amber-900/40">
            DQ Reasons: {signals.data_quality.reasons.join(' • ')}
          </div>
        )}
      </div>

      {/* Guardrail Divergence Alert if Policy Overrode Laya */}
      {isDiverged && (
        <div className="bg-amber-950/40 border border-amber-500/60 rounded-lg p-3 flex items-start gap-2.5 shadow-sm">
          <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <h5 className="font-bold text-amber-200">
              GUARDRAIL DIVERGENCE DETECTED (laya_guardrail_override)
            </h5>
            <p className="text-slate-300 mt-0.5">
              Deterministic policy finalized priority to{' '}
              <strong className="text-white font-mono">{decision?.priority}</strong>, modifying Laya&apos;s
              suggested priority of{' '}
              <strong className="text-amber-300 font-mono">{laya?.suggested_priority}</strong>. Invariants have final authority.
            </p>
          </div>
        </div>
      )}

      {/* Decision Authority Comparison: Laya Advisory vs Final Policy */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {/* Left: Laya Advisory Proposal */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2.5">
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-purple-400" />
                <h4 className="text-xs font-bold text-purple-300 uppercase tracking-wider">
                  Laya Advisory (Model Proposal)
                </h4>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800/40">
                  PROPOSES
                </span>
                <button
                  onClick={() => setAdvisoryVisible((v) => !v)}
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors"
                  title="Display filter only — policy authority and audit records are unaffected"
                >
                  {advisoryVisible ? 'HIDE ADVISORY' : 'SHOW ADVISORY'}
                </button>
              </div>
            </div>

            {!advisoryVisible ? (
              <div className="py-6 text-center text-xs text-slate-500 font-mono border border-dashed border-slate-800 rounded-lg">
                Laya advisory display disabled.
                <br />
                Display filter only — final decisions still governed by deterministic policy.
              </div>
            ) : laya ? (
              <div className="space-y-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Suggested Priority:</span>
                  <span
                    className={`font-mono font-bold px-2 py-0.5 rounded border text-xs ${getPriorityColor(
                      laya.suggested_priority
                    )}`}
                  >
                    {laya.suggested_priority || 'NONE'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Answer Confidence:</span>
                  <span className="font-mono font-bold text-purple-300">
                    {laya.answer_confidence_priority !== null &&
                    laya.answer_confidence_priority !== undefined
                      ? `${(laya.answer_confidence_priority * 100).toFixed(1)}%`
                      : 'N/A'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Status:</span>
                  <span
                    className={`font-mono font-bold px-2 py-0.5 rounded border text-[11px] ${
                      laya.status === 'ok'
                        ? 'text-emerald-300 bg-emerald-950/60 border-emerald-800/60'
                        : laya.status === 'unavailable'
                          ? 'text-red-300 bg-red-950/60 border-red-800/60'
                          : 'text-amber-300 bg-amber-950/60 border-amber-800/60'
                    }`}
                  >
                    laya_{laya.status}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Recommended Resource:</span>
                  <span className="font-mono text-slate-200 capitalize">
                    {laya.recommended_resource_type?.replace('_', ' ') || 'None'}
                  </span>
                </div>

                {Object.keys(laya.distribution || {}).length > 0 && (
                  <div>
                    <span className="text-slate-400 block mb-1">Probability Distribution:</span>
                    <div className="space-y-1">
                      {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((p) => {
                        const v = laya.distribution[p];
                        if (v === undefined) return null;
                        return (
                          <div key={p} className="flex items-center gap-2">
                            <span className="w-14 text-[10px] text-slate-500 font-mono">{p}</span>
                            <div className="flex-1 bg-slate-800 h-1.5 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-purple-500"
                                style={{ width: `${Math.min(v, 1) * 100}%` }}
                              />
                            </div>
                            <span className="w-12 text-right text-[10px] font-mono text-slate-300">
                              {(v * 100).toFixed(1)}%
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <span>Latency:</span>
                  <span>{laya.latency_ms.toFixed(1)} ms</span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <span>Checkpoint:</span>
                  <span className="text-slate-300 truncate max-w-[150px]" title={laya.checkpoint}>
                    {laya.checkpoint}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <span>Router / Device:</span>
                  <span className="text-slate-300">
                    {laya.router_model} @ {laya.device}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <span>Guardrail Applied:</span>
                  <span
                    className={
                      laya.guardrail_applied ? 'text-amber-400 font-bold' : 'text-slate-400'
                    }
                  >
                    {laya.guardrail_applied ? 'TRUE' : 'FALSE'}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <span>State Hash:</span>
                  <span className="text-slate-500 truncate max-w-[120px]" title={laya.state_hash}>
                    {laya.state_hash.substring(0, 10)}...
                  </span>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500 font-mono">
                No Laya advisory block recorded
              </div>
            )}
          </div>

          <div className="mt-3 pt-2 border-t border-slate-800/80 text-[10px] text-slate-500 font-mono">
            Laya never finalizes decisions (Invariant 5)
          </div>
        </div>

        {/* Right: Deterministic Policy Decision */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2.5">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-emerald-400" />
                <h4 className="text-xs font-bold text-emerald-300 uppercase tracking-wider">
                  Deterministic Policy (Final Authority)
                </h4>
              </div>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/40">
                DECIDES
              </span>
            </div>

            {decision ? (
              <div className="space-y-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Governed Priority:</span>
                  <span
                    className={`font-mono font-bold px-2 py-0.5 rounded border text-xs ${getPriorityColor(
                      decision.priority
                    )}`}
                  >
                    {decision.priority}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Decision State:</span>
                  <span
                    className={`font-mono font-bold px-2 py-0.5 rounded border text-xs ${getStateColor(
                      decision.state
                    )}`}
                  >
                    {decision.state}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Final Decision Source:</span>
                  <span className="font-mono text-slate-200">
                    {laya?.final_decision_source || 'policy_finalized'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Overall Confidence Gate:</span>
                  <span className="font-mono font-bold text-emerald-400">
                    {decision.overall_confidence !== null &&
                    decision.overall_confidence !== undefined
                      ? `${(decision.overall_confidence * 100).toFixed(1)}% (gate ≥60%)`
                      : 'N/A'}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <span>Policy Version:</span>
                  <span>{decision.policy_version}</span>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500 font-mono">
                No policy decision reached yet
              </div>
            )}
          </div>

          <div className="mt-3 pt-2 border-t border-slate-800/80 text-[10px] text-slate-500 font-mono">
            Deterministic rule guardrail has final authority
          </div>
        </div>
      </div>

      {/* Decision Lineage (enhancement 3) */}
      {decision && decision.lineage && (
        <div className="bg-slate-950/70 border border-cyan-900/50 rounded-lg p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <FileCheck className="w-3.5 h-3.5 text-cyan-400" />
            <h4 className="text-xs font-bold uppercase tracking-wider text-cyan-300">
              Decision Lineage
            </h4>
            {decision.lineage.clause_id && (
              <span className="ml-auto px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                {decision.lineage.clause_id}
              </span>
            )}
          </div>

          <div className="space-y-1.5">
            {decision.lineage.terms.map((term) => (
              <div key={term.label} className="flex items-center gap-2">
                <span className="text-[11px] font-mono text-slate-400 w-36 shrink-0">
                  {term.label}
                </span>
                <div className="flex-1 h-2 bg-slate-900 rounded overflow-hidden">
                  <div
                    className={`h-full rounded ${
                      term.direction === 'positive'
                        ? 'bg-emerald-500/70'
                        : term.direction === 'negative'
                          ? 'bg-red-500/70'
                          : 'bg-slate-600/70'
                    }`}
                    style={{ width: `${Math.round(term.score * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-slate-500 w-16 text-right">
                  {term.score.toFixed(2)}
                </span>
                <span
                  className={`text-[10px] font-mono w-14 text-right ${
                    term.direction === 'positive'
                      ? 'text-emerald-400'
                      : term.direction === 'negative'
                        ? 'text-red-400'
                        : 'text-slate-500'
                  }`}
                >
                  {term.direction}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-2 pt-2 border-t border-slate-800/80 text-[10px] font-mono text-slate-400 break-words">
            {decision.lineage.expression}
          </div>
        </div>
      )}

      {/* Stream Trust (enhancement 1) */}
      {decision?.trust && (
        <div
          className={`bg-slate-950/70 border rounded-lg p-3 ${
            decision.trust.flagged_sources.length > 0
              ? 'border-fuchsia-500/50'
              : 'border-slate-800'
          }`}
        >
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-fuchsia-400" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Stream Trust
              </h4>
            </div>
            <span
              className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded border ${
                decision.trust.mean_veracity < 0.7
                  ? 'bg-fuchsia-950/80 text-fuchsia-300 border-fuchsia-700/60'
                  : 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60'
              }`}
            >
              mean {decision.trust.mean_veracity.toFixed(2)}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(decision.trust.source_scores).map(([src, score]) => {
              const flagged = decision.trust!.flagged_sources.includes(src);
              return (
                <span
                  key={src}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                    flagged
                      ? 'bg-fuchsia-950/70 text-fuchsia-300 border-fuchsia-700/60'
                      : 'bg-slate-900 text-emerald-300 border-slate-700'
                  }`}
                  title={flagged ? 'Flagged — veracity below threshold' : 'Trusted stream'}
                >
                  {src} · {score.toFixed(2)}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Matched Rules & Structured Rationale */}
      {decision && (
        <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <FileCheck className="w-3.5 h-3.5 text-cyan-400" />
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Structured Policy Rules & Auditable Rationale
            </h4>
          </div>

          <div className="space-y-2">
            <div>
              <span className="text-[11px] text-slate-400 block mb-1">Matched Policy Rules:</span>
              <div className="flex flex-wrap gap-1.5">
                {decision.matched_rules && decision.matched_rules.length > 0 ? (
                  decision.matched_rules.map((rule) => (
                    <span
                      key={rule}
                      className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-900 text-indigo-300 border border-slate-700"
                    >
                      {rule}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-500 font-mono">No specific rules matched</span>
                )}
              </div>
            </div>

            <div>
              <span className="text-[11px] text-slate-400 block mb-1">Structured Reasons:</span>
              <ul className="space-y-1">
                {decision.reasons && decision.reasons.length > 0 ? (
                  decision.reasons.map((r, idx) => (
                    <li
                      key={idx}
                      className="text-xs font-mono text-slate-300 flex items-start gap-1.5 bg-slate-900/60 p-1.5 rounded border border-slate-800"
                    >
                      <span className="text-slate-500">•</span>
                      <span>{r}</span>
                    </li>
                  ))
                ) : (
                  <li className="text-xs text-slate-500 font-mono">No structured reasons</li>
                )}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Resource Allocation */}
      {decision && (
        <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Resource Dispatch Assignments
            </span>
            <span className="text-[10px] font-mono text-slate-400">
              Assigned: {decision.assigned_resource_ids.length}
            </span>
          </div>

          <div className="flex flex-wrap gap-2">
            {decision.assigned_resource_ids.length > 0 ? (
              decision.assigned_resource_ids.map((id) => (
                <span
                  key={id}
                  className="px-2.5 py-1 rounded-md text-xs font-mono font-semibold bg-emerald-950/70 text-emerald-300 border border-emerald-800/50 flex items-center gap-1.5"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{id}</span>
                </span>
              ))
            ) : (
              <span className="text-xs text-slate-500 font-mono">
                {decision.state === 'CONTENTION_ESCALATION'
                  ? 'Contention Escalation: No resources available in pool'
                  : 'No resources currently assigned to this incident'}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

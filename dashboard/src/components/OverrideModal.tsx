import type React from 'react';
import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Flame,
  Lock,
  UserCheck,
  X,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  DecisionRecord,
  ImpactPreviewResponse,
  OverrideContextCode,
  OverrideType,
  Priority,
} from '../types/api';

interface OverrideModalProps {
  decision: DecisionRecord;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const CONTEXT_CODE_LABELS: Record<OverrideContextCode, string> = {
  SCENE_REPORT: 'On-scene report / field observer',
  COMMAND_ORDER: 'Command order from superior',
  ROAD_CONDITION: 'Road condition not in model (e.g. unmapped blockage)',
  SENSOR_FAILURE: 'Sensor failure / stale telemetry',
  EXTERNAL_AGENCY: 'External agency coordination (fire/police liaison)',
  OTHER: 'Other external context',
};

export const OverrideModal: React.FC<OverrideModalProps> = ({
  decision,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [operatorId, setOperatorId] = useState('op-dispatcher-07');
  const [overrideType, setOverrideType] = useState<OverrideType>('CHANGE_PRIORITY');
  const [newPriority, setNewPriority] = useState<Priority>('CRITICAL');
  const [reason, setReason] = useState('');
  const [basis, setBasis] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [impact, setImpact] = useState<ImpactPreviewResponse | null>(null);
  const [impactAck, setImpactAck] = useState(false);
  const [contextCode, setContextCode] = useState<OverrideContextCode | ''>('');
  const [breakGlass, setBreakGlass] = useState(false);

  // enhancement 4: live risk preview — read-only dry run before submit
  useEffect(() => {
    if (!isOpen) return;
    let stale = false;
    api
      .impactPreview({
        decision_id: decision.decision_id,
        override_type: overrideType,
        new_priority: overrideType === 'CHANGE_PRIORITY' ? newPriority : null,
      })
      .then((res) => {
        if (!stale) setImpact(res);
      })
      .catch(() => {
        if (!stale) setImpact(null);
      });
    return () => {
      stale = true;
    };
  }, [isOpen, decision.decision_id, overrideType, newPriority]);

  const tier = impact?.tier ?? null;
  // reset acknowledgments when the risk tier changes (render-phase adjustment)
  const [prevTier, setPrevTier] = useState<string | null>(tier);
  if (prevTier !== tier) {
    setPrevTier(tier);
    setImpactAck(false);
    setContextCode('');
    setBreakGlass(false);
  }

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!operatorId.trim()) {
      setErrorMsg('Operator ID is required (Invariant 7)');
      return;
    }
    if (!basis) {
      setErrorMsg(
        'Override basis is required: cite the policy clause you are overriding, or mark a policy gap / external context',
      );
      return;
    }
    if (!reason.trim()) {
      setErrorMsg('Justification reason is required (Invariant 7)');
      return;
    }
    if (tier === 'BREAK_GLASS' && !breakGlass) {
      setErrorMsg(
        'BREAK-GLASS life-safety override requires explicit emergency acknowledgment (enhancement 4)',
      );
      return;
    }
    if (tier === 'HIGH' && (!impactAck || !contextCode)) {
      setErrorMsg(
        'HIGH-risk override requires impact acknowledgment and a context code (enhancement 4)',
      );
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    const isClause =
      basis !== 'POLICY_GAP' &&
      basis !== 'EXTERNAL_CONTEXT' &&
      decision.matched_rules.includes(basis);

    try {
      await api.applyOverride({
        operator_id: operatorId.trim(),
        decision_id: decision.decision_id,
        override_type: overrideType,
        reason: reason.trim(),
        new_priority: newPriority || null,
        cited_clause: isClause ? basis : null,
        reason_code: isClause
          ? 'POLICY_CLAUSE'
          : basis === 'POLICY_GAP'
            ? 'POLICY_GAP'
            : 'EXTERNAL_CONTEXT',
        impact_ack: impactAck,
        context_code: contextCode || null,
        break_glass: breakGlass,
      });

      onSuccess();
      onClose();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-lg w-full p-5 relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-2.5 mb-4 border-b border-slate-800 pb-3">
          <div className="p-2 bg-indigo-950/80 border border-indigo-500/40 rounded-lg text-indigo-400">
            <Lock className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              Apply Human Override
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/40">
                Invariant 7
              </span>
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Target Decision: {decision.decision_id} (Incident: {decision.incident_id})
            </p>
          </div>
        </div>

        {errorMsg && (
          <div className="mb-4 p-2.5 rounded-lg bg-red-950/80 border border-red-500/50 text-red-300 text-xs font-mono flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
          {/* Operator ID */}
          <div>
            <label className="text-[11px] font-semibold text-slate-300 block mb-1">
              Operator Identifier <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              required
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              placeholder="e.g. op-commander-01"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 font-mono focus:border-indigo-500 focus:outline-none"
            />
            <span className="text-[10px] text-slate-500 mt-0.5 block">
              Operator ID must be a non-empty string. System reserves &apos;system&apos;.
            </span>
          </div>

          {/* Override Type */}
          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="text-[11px] font-semibold text-slate-300 block mb-1">
                Override Action <span className="text-red-400">*</span>
              </label>
              <select
                value={overrideType}
                onChange={(e) => {
                  const t = e.target.value as OverrideType;
                  setOverrideType(t);
                  if (t === 'CHANGE_PRIORITY') setNewPriority('CRITICAL');
                }}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-slate-200 focus:border-indigo-500 focus:outline-none"
              >
                <option value="CHANGE_PRIORITY">CHANGE PRIORITY</option>
                <option value="ASSIGN_RESOURCES">ASSIGN RESOURCES</option>
                <option value="DISMISS_INCIDENT">DISMISS INCIDENT</option>
                <option value="ESCALATE_TO_HUMAN">ESCALATE TO HUMAN</option>
                <option value="MARK_DATA_UNTRUSTED">MARK DATA UNTRUSTED</option>
                <option value="OVERRIDE_AUTOMATION_HOLD">OVERRIDE AUTOMATION HOLD</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-semibold text-slate-300 block mb-1">
                New Governed Priority
              </label>
              <select
                value={newPriority}
                onChange={(e) => setNewPriority(e.target.value as Priority)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-slate-200 focus:border-indigo-500 focus:outline-none uppercase font-mono"
              >
                <option value="CRITICAL">CRITICAL</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </div>
          </div>

          {/* Override Basis (enhancement 3: clause attribution) */}
          <div>
            <label className="text-[11px] font-semibold text-slate-300 block mb-1">
              Override Basis <span className="text-red-400">*</span>
            </label>
            <select
              required
              value={basis}
              onChange={(e) => setBasis(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-slate-200 font-mono focus:border-indigo-500 focus:outline-none"
            >
              <option value="">Select the clause you are overriding…</option>
              {decision.matched_rules.map((rule) => (
                <option key={rule} value={rule}>
                  Cite clause: {rule}
                </option>
              ))}
              <option value="POLICY_GAP">Policy gap / incomplete policy</option>
              <option value="EXTERNAL_CONTEXT">External context not in policy</option>
            </select>
            <span className="text-[10px] text-slate-500 mt-0.5 block">
              Cited clause and reason code are written to the immutable audit log.
            </span>
          </div>

          {/* Impact preview (enhancement 4: zero-trust friction) */}
          {impact && (
            <div
              className={`p-2.5 rounded-lg border space-y-2 ${
                impact.tier === 'BREAK_GLASS'
                  ? 'bg-red-950/70 border-red-500/60'
                  : impact.tier === 'HIGH'
                    ? 'bg-amber-950/60 border-amber-500/50'
                    : 'bg-slate-950/60 border-slate-800'
              }`}
            >
              <div className="flex items-center gap-2">
                {impact.tier === 'BREAK_GLASS' ? (
                  <Flame className="w-4 h-4 shrink-0 text-red-400" />
                ) : (
                  <AlertTriangle
                    className={`w-4 h-4 shrink-0 ${
                      impact.tier === 'HIGH' ? 'text-amber-400' : 'text-slate-500'
                    }`}
                  />
                )}
                <span
                  className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border uppercase tracking-wide ${
                    impact.tier === 'BREAK_GLASS'
                      ? 'bg-red-900/80 text-red-300 border-red-500/60'
                      : impact.tier === 'HIGH'
                        ? 'bg-amber-900/70 text-amber-300 border-amber-500/50'
                        : 'bg-slate-900 text-slate-400 border-slate-700'
                  }`}
                >
                  {impact.tier} RISK
                </span>
              </div>
              <p
                className={`text-[11px] font-mono leading-snug ${
                  impact.tier === 'BREAK_GLASS'
                    ? 'text-red-200'
                    : impact.tier === 'HIGH'
                      ? 'text-amber-200'
                      : 'text-slate-400'
                }`}
              >
                {impact.warning}
              </p>

              {impact.requires_context_code && (
                <div>
                  <label className="text-[11px] font-semibold text-amber-300 block mb-1">
                    External Context Code <span className="text-red-400">*</span>
                  </label>
                  <select
                    value={contextCode}
                    onChange={(e) => setContextCode(e.target.value as OverrideContextCode | '')}
                    className="w-full bg-slate-950 border border-amber-500/40 rounded-lg px-2.5 py-2 text-slate-200 font-mono focus:border-amber-500 focus:outline-none"
                  >
                    <option value="">Select the external context justifying this override…</option>
                    {(
                      Object.entries(CONTEXT_CODE_LABELS) as [OverrideContextCode, string][]
                    ).map(([code, label]) => (
                      <option key={code} value={code}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {impact.requires_ack && (
                <label className="flex items-start gap-2 text-[11px] font-mono cursor-pointer">
                  <input
                    type="checkbox"
                    checked={impactAck}
                    onChange={(e) => setImpactAck(e.target.checked)}
                    className="mt-0.5 shrink-0 accent-amber-500"
                  />
                  <span className="text-amber-200">
                    I acknowledge the projected impact of this override (stored in the
                    immutable audit log with my operator identity).
                  </span>
                </label>
              )}

              {impact.requires_break_glass && (
                <label className="flex items-start gap-2 text-[11px] font-mono cursor-pointer">
                  <input
                    type="checkbox"
                    checked={breakGlass}
                    onChange={(e) => setBreakGlass(e.target.checked)}
                    className="mt-0.5 shrink-0 accent-red-500"
                  />
                  <span className="text-red-200 font-bold">
                    BREAK-GLASS: life-safety override — authorize immediate action, accept
                    mandatory post-event review (flagged in audit).
                  </span>
                </label>
              )}
            </div>
          )}

          {/* Justification Reason */}
          <div>
            <label className="text-[11px] font-semibold text-slate-300 block mb-1">
              Structured Justification & Rationale <span className="text-red-400">*</span>
            </label>
            <textarea
              required
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Provide verifiable situational context justifying this human override (e.g., on-scene report confirms hazmat leak)..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:border-indigo-500 focus:outline-none placeholder:text-slate-600"
            />
            <span className="text-[10px] text-slate-500 mt-0.5 block">
              Written permanently to the immutable audit log with cryptographic entry hash.
            </span>
          </div>

          {/* Automated Context Baseline */}
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 text-[11px] font-mono text-slate-400">
            Current automated baseline: <strong className="text-slate-200">{decision.priority}</strong> ({decision.state}) • Laya proposed: <strong className="text-purple-300">{decision.laya?.suggested_priority || 'N/A'}</strong>
          </div>

          {/* Modal Actions */}
          <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 rounded-lg text-slate-300 hover:bg-slate-800 border border-slate-700 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-all shadow-md shadow-indigo-900/40 flex items-center gap-1.5"
            >
              <UserCheck className="w-4 h-4" />
              <span>{isSubmitting ? 'Recording...' : 'Authorize & Sign Override'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

import type React from 'react';
import { useState } from 'react';
import {
  AlertTriangle,
  Lock,
  UserCheck,
  X,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  DecisionRecord,
  OverrideType,
  Priority,
} from '../types/api';

interface OverrideModalProps {
  decision: DecisionRecord;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

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
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!operatorId.trim()) {
      setErrorMsg('Operator ID is required (Invariant 7)');
      return;
    }
    if (!reason.trim()) {
      setErrorMsg('Justification reason is required (Invariant 7)');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await api.applyOverride({
        operator_id: operatorId.trim(),
        decision_id: decision.decision_id,
        override_type: overrideType,
        reason: reason.trim(),
        new_priority: newPriority || null,
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

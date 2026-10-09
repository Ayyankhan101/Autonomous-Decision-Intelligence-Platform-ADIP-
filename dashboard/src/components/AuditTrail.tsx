import type React from 'react';
import { useState } from 'react';
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Database,
  Search,
  User,
} from 'lucide-react';
import type { AuditEntry } from '../types/api';

interface AuditTrailProps {
  entries: AuditEntry[];
}

export const AuditTrail: React.FC<AuditTrailProps> = ({ entries }) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredEntries = entries.filter((e) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      e.entry_id.toLowerCase().includes(q) ||
      e.action.toLowerCase().includes(q) ||
      e.actor.toLowerCase().includes(q) ||
      (e.incident_id && e.incident_id.toLowerCase().includes(q)) ||
      (e.decision_id && e.decision_id.toLowerCase().includes(q)) ||
      e.reason.toLowerCase().includes(q)
    );
  });

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-md flex flex-col gap-4">
      {/* Header & Chain Validation Badge */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-amber-950/80 border border-amber-500/40 rounded-lg text-amber-400">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              Cryptographic Audit Log
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/50 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                <span>APPEND-ONLY • SHA-256 CHAINED</span>
              </span>
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Append-only SQLite • Hash-linked SHA-256 blocks (Phase 4)
            </p>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search audit entries..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:border-amber-500 focus:outline-none w-56 font-mono"
          />
        </div>
      </div>

      {/* Entries Table / List */}
      <div className="space-y-2 max-h-[650px] overflow-y-auto pr-1">
        {filteredEntries.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-500 font-mono">
            No audit records match your query
          </div>
        ) : (
          filteredEntries.map((entry) => {
            const isExpanded = expandedId === entry.entry_id;
            const isOverride = entry.action === 'OVERRIDE_APPLIED';

            return (
              <div
                key={entry.entry_id}
                className="bg-slate-950/70 border border-slate-800/80 rounded-lg overflow-hidden transition-all hover:border-slate-700"
              >
                {/* Entry Summary Row */}
                <div
                  onClick={() => toggleExpand(entry.entry_id)}
                  className="p-3 flex items-center justify-between gap-3 cursor-pointer select-none"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <button className="text-slate-400 hover:text-white">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </button>

                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs font-mono font-bold text-slate-200">
                        #{entry.entry_id}
                      </span>

                      <span
                        className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase tracking-wide ${
                          isOverride
                            ? 'bg-cyan-950 text-cyan-300 border-cyan-500/50'
                            : 'bg-indigo-950 text-indigo-300 border-indigo-500/50'
                        }`}
                      >
                        {entry.action}
                      </span>

                      {entry.break_glass && (
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase tracking-wide bg-red-950 text-red-300 border-red-500/60">
                          BREAK-GLASS
                        </span>
                      )}
                      {!entry.break_glass && entry.impact_tier === 'HIGH' && (
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase tracking-wide bg-amber-950 text-amber-300 border-amber-500/50">
                          IMPACT HIGH
                        </span>
                      )}

                      <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
                        <User className="w-3 h-3 text-slate-500" />
                        <strong className="text-slate-300">{entry.actor}</strong>
                      </span>

                      {entry.incident_id && (
                        <span className="text-[11px] font-mono text-slate-500 hidden sm:inline">
                          ({entry.incident_id})
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-[11px] font-mono text-slate-400">
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </span>

                    <span
                      className="text-[10px] font-mono text-slate-500 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800 truncate max-w-[90px] hidden md:inline"
                      title={`Entry Hash: ${entry.entry_hash}`}
                    >
                      {entry.entry_hash.substring(0, 8)}...
                    </span>
                  </div>
                </div>

                {/* Expanded Details Drawer */}
                {isExpanded && (
                  <div className="bg-slate-900/90 border-t border-slate-800/80 p-3.5 space-y-3 text-xs font-mono animate-in fade-in duration-150">
                    {/* Reason */}
                    {entry.reason && (
                      <div>
                        <span className="text-[10px] uppercase text-slate-500 block mb-0.5">
                          Rationale / Reason:
                        </span>
                        <p className="text-xs text-slate-200 bg-slate-950 p-2 rounded border border-slate-800">
                          {entry.reason}
                        </p>
                      </div>
                    )}

                    {/* Metadata & Versions Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                      <div className="bg-slate-950 p-2 rounded border border-slate-800">
                        <span className="text-slate-500 block">Decision ID:</span>
                        <span className="text-slate-200">{entry.decision_id || 'N/A'}</span>
                      </div>
                      <div className="bg-slate-950 p-2 rounded border border-slate-800">
                        <span className="text-slate-500 block">Policy Version:</span>
                        <span className="text-slate-200">{entry.policy_version || 'N/A'}</span>
                      </div>
                    </div>

                    {/* Attribution & impact (enhancements 3+4) */}
                    {(entry.cited_clause || entry.impact_tier || entry.context_code) && (
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
                        <div className="bg-slate-950 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Override Basis:</span>
                          <span className="text-slate-200">
                            {entry.cited_clause || 'N/A'}
                            {entry.reason_code ? ` · ${entry.reason_code}` : ''}
                          </span>
                        </div>
                        <div className="bg-slate-950 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Impact Tier:</span>
                          <span
                            className={
                              entry.break_glass
                                ? 'text-red-300 font-bold'
                                : entry.impact_tier === 'HIGH'
                                  ? 'text-amber-300 font-bold'
                                  : 'text-slate-200'
                            }
                          >
                            {entry.impact_tier || 'N/A'}
                          </span>
                        </div>
                        <div className="bg-slate-950 p-2 rounded border border-slate-800">
                          <span className="text-slate-500 block">Context Code:</span>
                          <span className="text-slate-200">{entry.context_code || 'N/A'}</span>
                        </div>
                      </div>
                    )}

                    {/* Laya Metadata Block */}
                    {entry.laya && entry.laya.laya_checkpoint && (
                      <div className="bg-purple-950/20 border border-purple-900/40 p-2.5 rounded-lg space-y-1.5">
                        <div className="flex items-center gap-1.5 text-purple-300 font-bold text-[11px]">
                          <Brain className="w-3.5 h-3.5 text-purple-400" />
                          <span>Recorded Laya Advisory Metadata (Phase 4 Block)</span>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[10px] text-slate-300">
                          <div>
                            <span className="text-slate-500 block">Checkpoint:</span>
                            <span className="text-slate-300 truncate block">
                              {entry.laya.laya_checkpoint}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block">Status:</span>
                            <span className="text-slate-200 font-bold uppercase">
                              {entry.laya.laya_status || 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block">Questions Ver:</span>
                            <span className="text-cyan-300 font-mono">
                              {entry.laya.laya_questions_version || 'q-0.1.0'}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block">Suggested Priority:</span>
                            <span className="text-purple-300 font-bold">
                              {entry.laya.laya_suggested_priority || 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block">Answer Confidence:</span>
                            <span>
                              {entry.laya.laya_answer_confidence_priority !== null &&
                              entry.laya.laya_answer_confidence_priority !== undefined
                                ? `${(entry.laya.laya_answer_confidence_priority * 100).toFixed(1)}%`
                                : 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block">Guardrail Modified:</span>
                            <span
                              className={
                                entry.laya.laya_guardrail_modified ? 'text-amber-400' : 'text-slate-400'
                              }
                            >
                              {entry.laya.laya_guardrail_modified ? 'TRUE' : 'FALSE'}
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Cryptographic Hashes */}
                    <div className="space-y-1 pt-1 border-t border-slate-800 text-[10px] text-slate-500">
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-400">Previous Hash:</span>
                        <span className="text-slate-300 truncate" title={entry.previous_hash}>
                          {entry.previous_hash}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-400">Entry Hash:</span>
                        <span className="text-emerald-400 font-bold truncate" title={entry.entry_hash}>
                          {entry.entry_hash}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

import type React from 'react';
import { useState } from 'react';
import { Link2, ShieldCheck, ShieldX, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import type { AuditEntry, AuditVerifyResponse, NewIds } from '../types/api';

interface AuditChainProps {
  entries: AuditEntry[];
  newIds?: NewIds;
}

const CHAIN_LEN = 8;

export const AuditChain: React.FC<AuditChainProps> = ({ entries, newIds }) => {
  const [verify, setVerify] = useState<AuditVerifyResponse | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);

  // chronological, newest last; show the last CHAIN_LEN
  const window = entries.slice(-CHAIN_LEN);

  const handleVerify = async () => {
    setIsVerifying(true);
    try {
      const res = await api.auditVerify();
      setVerify(res);
    } catch {
      setVerify({
        ok: false,
        entry_count: -1,
        broken_at: null,
      });
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-md">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Link2 className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Hash Chain — Live View
          </h3>
          <span className="text-[10px] font-mono text-slate-500">
            last {window.length} of {entries.length}
          </span>
        </div>
        <button
          onClick={handleVerify}
          disabled={isVerifying}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-950 hover:bg-cyan-900 text-cyan-200 border border-cyan-800/50 flex items-center gap-1.5 transition-all disabled:opacity-60"
          title="Recompute every entry hash server-side, now"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isVerifying ? 'animate-spin' : ''}`} />
          <span>{isVerifying ? 'Verifying…' : 'Verify Chain Now'}</span>
        </button>
      </div>

      {verify && (
        <div
          className={`mb-3 p-2.5 rounded-lg border text-xs font-mono flex items-center gap-2 ${
            verify.ok
              ? 'bg-emerald-950/70 text-emerald-200 border-emerald-500/50'
              : 'bg-red-950/80 text-red-200 border-red-500/60'
          }`}
        >
          {verify.ok ? (
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <ShieldX className="w-4 h-4 text-red-400 shrink-0" />
          )}
          <span>
            {verify.ok
              ? `CHAIN INTACT — ${verify.entry_count} entries rehashed, genesis → head verified`
              : verify.entry_count < 0
                ? 'VERIFY FAILED — backend unreachable'
                : `CHAIN BROKEN at entry #${verify.broken_at} of ${verify.entry_count}`}
          </span>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        {window.map((entry, i) => {
          const isNew = newIds?.audit.includes(entry.entry_id) ?? false;
          return (
            <div key={entry.entry_id} className="flex items-center gap-2 min-w-0">
              <div
                className={`flex-1 min-w-0 bg-slate-950/80 border rounded-lg px-2.5 py-1.5 flex items-center gap-2 transition-all ${
                  isNew
                    ? 'border-cyan-400 ring-1 ring-cyan-400/50 shadow-[0_0_8px_rgba(34,211,238,0.3)]'
                    : 'border-slate-800/80'
                }`}
              >
                <span className="text-[10px] font-mono text-slate-500 shrink-0">
                  #{entry.entry_id.replace('aud-', '')}
                </span>
                <span className="text-[10px] font-mono font-bold text-indigo-300 truncate">
                  {entry.action}
                </span>
                <span className="text-[10px] font-mono text-slate-500 truncate">
                  {entry.actor}
                </span>
                <span className="ml-auto text-[10px] font-mono text-cyan-400/80 shrink-0">
                  {entry.entry_hash.replace('sha256:', '').slice(0, 10)}…
                </span>
              </div>
              {i < window.length - 1 && (
                <span
                  className="text-[9px] font-mono text-slate-600 shrink-0"
                  title={entry.entry_hash}
                >
                  ▼
                </span>
              )}
            </div>
          );
        })}
        {window.length === 0 && (
          <div className="text-xs font-mono text-slate-600 text-center py-4">
            No audit entries yet — start the simulation
          </div>
        )}
      </div>
    </div>
  );
};

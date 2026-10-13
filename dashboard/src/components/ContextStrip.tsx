import type React from 'react';
import { AlertTriangle, Cloud, ExternalLink, Info } from 'lucide-react';
import type { FeedsResponse } from '../types/api';

interface ContextStripProps {
  feeds: FeedsResponse | null;
}

function weatherLabel(tempC: number | null | undefined): string {
  if (tempC == null) return '—';
  return `${tempC}°C`;
}

export const ContextStrip: React.FC<ContextStripProps> = ({ feeds }) => {
  if (!feeds || feeds.mode !== 'live') return null;

  const weather = feeds.weather;
  const gdacs = feeds.feeds.find((f) => f.name === 'gdacs');
  const reliefweb = feeds.advisories[0];

  const hasAny = weather || gdacs?.ok || reliefweb;
  if (!hasAny) {
    return (
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl px-3 py-2 text-xs text-slate-500 font-mono flex items-center gap-2">
        <Info className="w-3.5 h-3.5 text-slate-600" />
        <span>Awaiting live feed data…</span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2 text-xs font-mono">
      {/* Weather chip */}
      <div className="flex items-center gap-1.5 bg-slate-900/80 border border-slate-800 rounded-md px-2.5 py-1 text-slate-300">
        <Cloud className="w-3.5 h-3.5 text-cyan-400" />
        <span>{weatherLabel(weather?.temperature_c)}</span>
        {weather?.precipitation_mm != null && weather.precipitation_mm > 0 && (
          <span className="text-cyan-400">· {weather.precipitation_mm}mm</span>
        )}
        {weather?.flood_risk && (
          <span className="px-1.5 py-0.5 bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded text-[10px]">
            FLOOD RISK
          </span>
        )}
      </div>

      {/* GDACS alert chip */}
      {gdacs && (
        <div
          className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 border ${
            gdacs.ok
              ? 'bg-slate-900/80 border-slate-800 text-slate-300'
              : 'bg-amber-950/60 border-amber-500/40 text-amber-200'
          }`}
          title={gdacs.detail || undefined}
        >
          {gdacs.ok ? (
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          ) : (
            <Info className="w-3.5 h-3.5 text-amber-500" />
          )}
          <span className="uppercase tracking-wider">GDACS</span>
          {gdacs.ok ? (
            <span>· {gdacs.total_events} alert{gdacs.total_events === 1 ? '' : 's'}</span>
          ) : (
            <span>· unavailable</span>
          )}
        </div>
      )}

      {/* Last ReliefWeb advisory */}
      {reliefweb && (
        <a
          href={reliefweb.url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 bg-slate-900/80 border border-slate-800 rounded-md px-2.5 py-1 text-slate-400 hover:text-slate-200 hover:border-slate-700 transition-colors"
        >
          <Info className="w-3.5 h-3.5 text-indigo-400" />
          <span className="max-w-[300px] truncate">{reliefweb.title}</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      )}
    </div>
  );
};

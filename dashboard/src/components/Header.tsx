import type React from 'react';
import { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Brain,
  Clock,
  Compass,
  Cpu,
  FileText,
  Leaf,
  Pause,
  RefreshCw,
  Scale,
  Sliders,
  Timer,
  Wifi,
  WifiOff,
} from 'lucide-react';
import type { StatePayload } from '../types/api';

interface HeaderProps {
  state: StatePayload | null;
  isConnected: boolean;
  isRefreshing: boolean;
  activeTab: 'command' | 'whatif' | 'audit';
  setActiveTab: (tab: 'command' | 'whatif' | 'audit') => void;
  onRefresh: () => void;
  onTogglePlayPause: () => void;
  lastUpdatedAt?: number | null;
}

export const Header: React.FC<HeaderProps> = ({
  state,
  isConnected,
  isRefreshing,
  activeTab,
  setActiveTab,
  onRefresh,
  onTogglePlayPause,
  lastUpdatedAt,
}) => {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const agoSec =
    lastUpdatedAt != null ? Math.max(0, Math.round((now - lastUpdatedAt) / 1000)) : null;

  const formatSimTime = (isoString?: string) => {
    if (!isoString) return '--:--:--';
    try {
      const d = new Date(isoString);
      return d.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    } catch {
      return isoString;
    }
  };

  const getLayaStatusBadge = () => {
    if (!state) return null;
    const mode = state.laya_mode;
    const status = state.last_laya_status || 'ok';

    let badgeColor = 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40';
    let icon = <Brain className="w-3.5 h-3.5 text-emerald-400" />;

    if (status === 'circuit_open' || status === 'unavailable') {
      badgeColor = 'bg-red-950/80 text-red-300 border-red-500/40';
      icon = <AlertTriangle className="w-3.5 h-3.5 text-red-400" />;
    } else if (status === 'timeout' || status === 'degraded' || status === 'invalid_output') {
      badgeColor = 'bg-amber-950/80 text-amber-300 border-amber-500/40';
      icon = <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />;
    }

    return (
      <div
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border ${badgeColor}`}
        title={`Laya Mode: ${mode}, Status: ${status}`}
      >
        {icon}
        <span className="font-semibold uppercase tracking-wider">Laya ({mode})</span>
        <span className="text-slate-400">|</span>
        <span className="capitalize">{status}</span>
      </div>
    );
  };

  return (
    <header className="bg-slate-900/90 border-b border-slate-800 backdrop-blur px-4 py-2.5 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-30 shadow-lg shadow-black/20">
      {/* Brand & City ID */}
      <div className="flex items-center gap-3">
        <div className="p-2 bg-indigo-600/20 border border-indigo-500/30 rounded-lg text-indigo-400">
          <Activity className="w-5 h-5 text-indigo-400 animate-pulse" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              JevCity <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/50">ADIP v0.1.0</span>
            </h1>
            <span className="text-slate-500 text-xs">•</span>
            <span className="text-xs font-mono text-slate-400">PORT 8200</span>
          </div>
          <p className="text-xs text-slate-400">Autonomous Decision Intelligence Platform</p>
        </div>
      </div>

      {/* Center status indicators */}
      <div className="flex flex-wrap items-center gap-2.5 text-xs">
        {/* Sim Clock */}
        <div className="flex items-center gap-2 px-3 py-1 bg-slate-950/80 border border-slate-800 rounded-md font-mono">
          <Clock className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-slate-400">Sim Clock:</span>
          <span className="font-semibold text-cyan-300">
            {formatSimTime(state?.simulated_time)}
          </span>
          <button
            onClick={onTogglePlayPause}
            className={`ml-1 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide flex items-center gap-1 transition-colors ${
              state?.running
                ? 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/30'
                : 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/30'
            }`}
            title={state?.running ? 'Pause simulation' : 'Resume simulation'}
          >
            {state?.running ? (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                <span>LIVE</span>
              </>
            ) : (
              <>
                <Pause className="w-2.5 h-2.5" />
                <span>PAUSED</span>
              </>
            )}
          </button>
        </div>

        {/* Seeds */}
        {state && (
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-slate-950/60 border border-slate-800/80 rounded-md font-mono text-slate-400 text-xs">
            <Sliders className="w-3.5 h-3.5 text-slate-400" />
            <span>Seeds:</span>
            <span className="text-slate-200">S:{state.session_seed} / R:{state.scenario_seed}</span>
          </div>
        )}

        {/* Policy Position Badge */}
        {state?.policy_position && (
          <div
            className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border ${
              state.policy_position === 'EQUITY'
                ? 'bg-violet-950/60 text-violet-300 border-violet-500/40'
                : state.policy_position === 'ECO'
                  ? 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40'
                  : 'bg-sky-950/60 text-sky-300 border-sky-500/40'
            }`}
            title="Active policy position (runtime switchable from the Policy Sandbox card)"
          >
            {state.policy_position === 'EQUITY' ? (
              <Scale className="w-3.5 h-3.5" />
            ) : state.policy_position === 'ECO' ? (
              <Leaf className="w-3.5 h-3.5" />
            ) : (
              <Timer className="w-3.5 h-3.5" />
            )}
            <span className="font-semibold tracking-wider">{state.policy_position}</span>
          </div>
        )}

        {/* Laya Runtime Badge */}
        {getLayaStatusBadge()}

        {/* Freshness ticker */}
        {agoSec != null && isConnected && (
          <div
            className="hidden lg:flex items-center gap-1 px-2 py-1 bg-slate-950/60 border border-slate-800/80 rounded-md font-mono text-[10px] text-slate-500"
            title="Seconds since last successful poll — proof the feed is live"
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                agoSec <= 2 ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
            />
            <span>upd {agoSec}s ago</span>
          </div>
        )}

        {/* Connection status */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border ${
            isConnected
              ? 'bg-emerald-950/40 text-emerald-400 border-emerald-500/30'
              : 'bg-red-950/80 text-red-300 border-red-500/50 animate-pulse'
          }`}
        >
          {isConnected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
          <span>{isConnected ? 'ONLINE' : 'UNREACHABLE'}</span>
        </div>
      </div>

      {/* Navigation tabs & actions */}
      <div className="flex items-center gap-2">
        <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            onClick={() => setActiveTab('command')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 ${
              activeTab === 'command'
                ? 'bg-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Compass className="w-3.5 h-3.5" />
            <span>Command Center</span>
          </button>
          <button
            onClick={() => setActiveTab('whatif')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 ${
              activeTab === 'whatif'
                ? 'bg-purple-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>What-If Sandbox</span>
          </button>
          <button
            onClick={() => setActiveTab('audit')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 ${
              activeTab === 'audit'
                ? 'bg-amber-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Audit Trail</span>
          </button>
        </div>

        <button
          onClick={onRefresh}
          className={`p-2 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 transition-colors ${
            isRefreshing ? 'animate-spin text-indigo-400' : ''
          }`}
          title="Refresh Data"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};

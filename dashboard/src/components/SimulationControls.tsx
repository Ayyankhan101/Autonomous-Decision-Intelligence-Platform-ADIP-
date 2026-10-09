import type React from 'react';
import { useState } from 'react';
import {
  Flame,
  Play,
  Pause,
  RotateCcw,
  Send,
  ShieldAlert,
  Zap,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  IncidentType,
  InjectionMode,
  Zone,
} from '../types/api';

interface SimulationControlsProps {
  running: boolean;
  sessionSeed: number;
  scenarioSeed: number;
  incidentCount: number;
  decisionCount: number;
  onRefresh: () => void;
}

export const SimulationControls: React.FC<SimulationControlsProps> = ({
  running,
  sessionSeed,
  scenarioSeed,
  incidentCount,
  decisionCount,
  onRefresh,
}) => {
  const [sSeed, setSSeed] = useState(sessionSeed);
  const [rSeed, setRSeed] = useState(scenarioSeed);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // Inject incident form state
  const [incType, setIncType] = useState<IncidentType>('accident');
  const [incZone, setIncZone] = useState<Zone>('east');
  const [incSeverity, setIncSeverity] = useState('moderate');
  const [incNotes, setIncNotes] = useState('');
  const [multiReport, setMultiReport] = useState(false);

  // Bad data injection state
  const [badDataMode, setBadDataMode] = useState<InjectionMode>('adversarial_notes');

  const showToast = (text: string, type: 'success' | 'error' = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 4000);
  };

  const hasSessionData = incidentCount > 0 || decisionCount > 0;

  const handleTogglePlayPause = async () => {
    setIsSubmitting(true);
    try {
      if (running) {
        await api.pauseSimulation();
        showToast('Simulation paused');
      } else if (hasSessionData) {
        await api.resumeSimulation();
        showToast('Simulation resumed');
      } else {
        await api.startSimulation({ session_seed: sSeed, scenario_seed: rSeed });
        showToast('Simulation started');
      }
      onRefresh();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = async () => {
    setIsSubmitting(true);
    try {
      await api.resetSimulation(sSeed, rSeed);
      showToast(`Simulation reset with seeds S:${sSeed} / R:${rSeed}`);
      onRefresh();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInjectIncident = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const res = await api.injectIncident({
        incident_type: incType,
        zone: incZone,
        severity: incSeverity,
        notes: incNotes || undefined,
        multi_report: multiReport,
      });
      showToast(`Incident injected: ${res.incident_id || 'OK'}`);
      setIncNotes('');
      onRefresh();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInjectBadData = async () => {
    setIsSubmitting(true);
    try {
      const res = await api.injectBadData({ mode: badDataMode });
      showToast(`Bad data injected (${badDataMode}): ${res.incident_id || 'OK'}`);
      onRefresh();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSecondEmergency = async () => {
    setIsSubmitting(true);
    try {
      const res = await api.injectSecondEmergency({ incident_type: 'fire', zone: 'north' });
      showToast(`Second Emergency triggered: ${res.incident_id || 'OK'}`);
      onRefresh();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-md flex flex-col gap-4">
      {/* Toast Alert */}
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

      {/* Primary Simulator Controls */}
      <div>
        <div className="flex items-center justify-between mb-2.5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Simulation Clock & Seeds
          </h3>
          <span className="text-[10px] font-mono text-slate-500">SeedConfig Invariant 11</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleTogglePlayPause}
            disabled={isSubmitting}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm ${
              running
                ? 'bg-amber-600 hover:bg-amber-500 text-white'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white'
            }`}
          >
            {running ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>
              {running ? 'Pause Sim' : hasSessionData ? 'Resume Sim' : 'Start Sim'}
            </span>
          </button>

          <button
            onClick={handleReset}
            disabled={isSubmitting}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition-all"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset</span>
          </button>

          <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800 text-xs font-mono">
            <span className="text-slate-400">S:</span>
            <input
              type="number"
              value={sSeed}
              onChange={(e) => setSSeed(Number(e.target.value))}
              className="w-12 bg-transparent text-white focus:outline-none"
              title="Session Seed"
            />
            <span className="text-slate-600">/</span>
            <span className="text-slate-400">R:</span>
            <input
              type="number"
              value={rSeed}
              onChange={(e) => setRSeed(Number(e.target.value))}
              className="w-12 bg-transparent text-white focus:outline-none"
              title="Scenario Seed"
            />
          </div>
        </div>
      </div>

      {/* Inject Incident Form */}
      <form onSubmit={handleInjectIncident} className="border-t border-slate-800/80 pt-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-2 flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-yellow-400" />
          <span>Simulate Incident</span>
        </h4>

        <div className="grid grid-cols-2 gap-2 text-xs mb-2">
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">Type</label>
            <select
              value={incType}
              onChange={(e) => setIncType(e.target.value as IncidentType)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1.5 text-slate-200 focus:border-indigo-500 focus:outline-none capitalize"
            >
              <option value="accident">Accident</option>
              <option value="fire">Fire</option>
              <option value="flood">Flood</option>
              <option value="traffic_spike">Traffic Spike</option>
            </select>
          </div>

          <div>
            <label className="text-[10px] text-slate-400 block mb-1">Zone</label>
            <select
              value={incZone}
              onChange={(e) => setIncZone(e.target.value as Zone)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1.5 text-slate-200 focus:border-indigo-500 focus:outline-none capitalize"
            >
              <option value="north">North Sector</option>
              <option value="central">Central Core</option>
              <option value="east">East Corridor</option>
              <option value="south">South District</option>
              <option value="west">West Sector</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs mb-2">
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">Severity Hint</label>
            <select
              value={incSeverity}
              onChange={(e) => setIncSeverity(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1.5 text-slate-200 focus:border-indigo-500 focus:outline-none capitalize"
            >
              <option value="minor">Minor</option>
              <option value="moderate">Moderate</option>
              <option value="severe">Severe</option>
            </select>
          </div>

          <div className="flex items-center gap-2 pt-4">
            <input
              type="checkbox"
              id="multiReport"
              checked={multiReport}
              onChange={(e) => setMultiReport(e.target.checked)}
              className="rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-0"
            />
            <label htmlFor="multiReport" className="text-[11px] text-slate-300">
              Multi-report (contradiction)
            </label>
          </div>
        </div>

        <div className="mb-2.5">
          <input
            type="text"
            placeholder="Incident notes (optional free text)..."
            value={incNotes}
            onChange={(e) => setIncNotes(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none placeholder:text-slate-600"
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center gap-1.5 shadow-sm transition-all"
        >
          <Send className="w-3.5 h-3.5" />
          <span>Inject Incident</span>
        </button>
      </form>

      {/* Bad Data & Adversarial Injection */}
      <div className="border-t border-slate-800/80 pt-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-2 flex items-center gap-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
          <span>Adversarial & Fault Injection</span>
        </h4>

        <div className="flex gap-2 mb-2">
          <select
            value={badDataMode}
            onChange={(e) => setBadDataMode(e.target.value as InjectionMode)}
            className="flex-1 bg-slate-950 border border-slate-800 rounded px-2 py-1.5 text-xs text-slate-200 focus:border-rose-500 focus:outline-none"
          >
            <option value="adversarial_notes">Adversarial Notes (Prompt Injection)</option>
            <option value="conflicting_reports">Conflicting Reports</option>
            <option value="missing_fields">Missing Critical Fields</option>
            <option value="out_of_range">Out-of-Range Coordinates</option>
          </select>

          <button
            onClick={handleInjectBadData}
            disabled={isSubmitting}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800/50 shadow-sm transition-all"
          >
            Inject Fault
          </button>
        </div>

        {/* Second emergency trigger for contention */}
        <button
          onClick={handleSecondEmergency}
          disabled={isSubmitting}
          className="w-full py-1.5 rounded-lg text-xs font-semibold bg-amber-950/70 hover:bg-amber-900/70 text-amber-300 border border-amber-800/50 flex items-center justify-center gap-1.5 shadow-sm transition-all mt-1"
          title="Fires a major second emergency in North Sector to trigger resource contention"
        >
          <Flame className="w-3.5 h-3.5 text-amber-400" />
          <span>Trigger Second Emergency (Contention Test)</span>
        </button>
      </div>
    </div>
  );
};

import { useState } from 'react';
import { useDashboardData } from './hooks/useDashboardData';
import { Header } from './components/Header';
import { KpiStrip } from './components/KpiStrip';
import { MapLayer } from './components/MapLayer';
import { IncidentInspector } from './components/IncidentInspector';
import { SimulationControls } from './components/SimulationControls';
import { PolicySandbox } from './components/PolicySandbox';
import { OverrideModal } from './components/OverrideModal';
import { AuditChain } from './components/AuditChain';
import { AuditTrail } from './components/AuditTrail';
import { WhatIfSandbox } from './components/WhatIfSandbox';
import { AlertTriangle, ShieldAlert, WifiOff } from 'lucide-react';
import { api } from './services/api';

export function App() {
  const {
    state,
    incidents,
    decisions,
    resources,
    auditEntries,
    selectedIncidentId,
    setSelectedIncidentId,
    selectedIncident,
    selectedDecision,
    isConnected,
    lastError,
    isRefreshing,
    newIds,
    latencySeries,
    lastUpdatedAt,
    refresh,
  } = useDashboardData(1500);

  const [activeTab, setActiveTab] = useState<'command' | 'whatif' | 'audit'>('command');
  const [isOverrideModalOpen, setIsOverrideModalOpen] = useState(false);

  const contentionCount = new Set(
    decisions.filter((d) => d.state === 'CONTENTION_ESCALATION').map((d) => d.incident_id),
  ).size;
  const badDataCount = new Set(
    [
      ...incidents.filter((i) => i.validation_status === 'hard_rejected').map((i) => i.incident_id),
      ...decisions.filter((d) => d.state === 'REJECTED_INPUT').map((d) => d.incident_id),
    ],
  ).size;

  const handleTogglePlayPause = async () => {
    if (!state) return;
    try {
      if (state.running) {
        await api.pauseSimulation();
      } else {
        await api.resumeSimulation();
      }
      refresh();
    } catch {
      // handled by hook on next tick
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Command Center Header */}
      <Header
        state={state}
        isConnected={isConnected}
        isRefreshing={isRefreshing}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onRefresh={refresh}
        onTogglePlayPause={handleTogglePlayPause}
        lastUpdatedAt={lastUpdatedAt}
      />

      {/* Connectivity Alert Banner */}
      {!isConnected && (
        <div className="bg-red-950/90 border-b border-red-500/50 px-4 py-2 text-xs font-mono text-red-200 flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-2">
            <WifiOff className="w-4 h-4 text-red-400 animate-pulse" />
            <span>
              <strong>BACKEND UNREACHABLE:</strong> Failed to connect to JevCity API at{' '}
              <code>http://localhost:8200</code>. Ensure the backend server is running.
            </span>
          </div>
          {lastError && <span className="text-[10px] text-red-400">({lastError})</span>}
        </div>
      )}

      {/* Contention Alert */}
      {contentionCount > 0 && (
        <div className="bg-amber-950/80 border-b border-amber-500/50 px-4 py-1.5 text-xs font-mono text-amber-200 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          <span>
            <strong>CONTENTION ALERT:</strong> {contentionCount} incident
            {contentionCount === 1 ? '' : 's'} escalated to CONTENTION_ESCALATION — resource pool
            exhausted.
          </span>
        </div>
      )}

      {/* Bad-Data Hold */}
      {badDataCount > 0 && (
        <div className="bg-rose-950/80 border-b border-rose-500/50 px-4 py-1.5 text-xs font-mono text-rose-200 flex items-center gap-2">
          <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
          <span>
            <strong>BAD-DATA HOLD:</strong> {badDataCount} incident
            {badDataCount === 1 ? '' : 's'} hard-rejected by ingestion validation — held for
            human review, never acted on silently.
          </span>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 p-4 max-w-7xl w-full mx-auto space-y-4">
        {activeTab === 'command' && (
          <div className="space-y-4">
            {/* Live KPI strip — real telemetry from the polled feed */}
            <KpiStrip
              state={state}
              incidents={incidents}
              decisions={decisions}
              resources={resources}
              latencySeries={latencySeries}
            />

            {/* Top: Map Layer & Resource Deployment Grid */}
            <MapLayer
              incidents={incidents}
              decisions={decisions}
              resources={resources}
              selectedIncidentId={selectedIncidentId}
              onSelectIncident={(id) => setSelectedIncidentId(id)}
              newIncidentIds={newIds.incidents}
            />

            {/* Bottom: Split Pane (Incident Inspection on left, Simulation Controls on right) */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2">
                <IncidentInspector
                  incident={selectedIncident}
                  decision={selectedDecision}
                  onOpenOverrideModal={() => setIsOverrideModalOpen(true)}
                />
              </div>

              <div className="lg:col-span-1 space-y-4">
                <SimulationControls
                  running={state?.running ?? false}
                  sessionSeed={state?.session_seed ?? 42}
                  scenarioSeed={state?.scenario_seed ?? 7}
                  incidentCount={state?.incident_count ?? 0}
                  decisionCount={state?.decision_count ?? 0}
                  onRefresh={refresh}
                  layaMode={state?.laya_mode ?? 'mock'}
                />

                <PolicySandbox
                  position={state?.policy_position ?? 'RESPONSE_TIME'}
                  objectiveWeights={state?.objective_weights}
                  onRefresh={refresh}
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'whatif' && (
          <WhatIfSandbox latestDecision={selectedDecision} />
        )}

        {activeTab === 'audit' && (
          <>
            <AuditChain entries={auditEntries} newIds={newIds} />
            <AuditTrail entries={auditEntries} newIds={newIds} />
          </>
        )}
      </main>

      {/* Human Override Modal (Invariant 7) */}
      {selectedDecision && (
        <OverrideModal
          decision={selectedDecision}
          isOpen={isOverrideModalOpen}
          onClose={() => setIsOverrideModalOpen(false)}
          onSuccess={() => {
            refresh();
          }}
        />
      )}
    </div>
  );
}

export default App;

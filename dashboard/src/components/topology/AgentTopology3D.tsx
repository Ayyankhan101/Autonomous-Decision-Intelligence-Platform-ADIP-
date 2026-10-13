import { Component, Suspense, useEffect, type ReactNode } from 'react';
import { Canvas } from '@react-three/fiber';
import { TopologyScene } from './Scene';
import { Hud } from './Hud';
import { useTopologyStore } from '../../stores/topologyStore';
import type { TopologyDashboardSnapshot } from '../../stores/topologyStore';
import { Radar } from 'lucide-react';

class TopologyErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; message: string }
> {
  state = { hasError: false, message: '' };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error.message };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-full flex flex-col items-center justify-center gap-2 text-center px-6">
          <div className="text-rose-400 font-mono text-sm">TOPOLOGY RENDERER CRASHED</div>
          <div className="text-slate-500 font-mono text-xs max-w-md break-words">
            {this.state.message}
          </div>
          <div className="text-slate-600 font-mono text-[10px]">
            Command / What-If / Audit tabs remain unaffected.
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function AwaitingTelemetry() {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3 text-slate-500">
      <Radar className="w-8 h-8 animate-pulse text-cyan-500/60" />
      <div className="font-mono text-xs tracking-widest">AWAITING TELEMETRY</div>
      <div className="font-mono text-[10px] text-slate-600">
        waiting for /api/dashboard — start the backend or check Command tab connectivity
      </div>
    </div>
  );
}

export function AgentTopology3D({ snapshot, onRefresh }: {
  snapshot: TopologyDashboardSnapshot;
  onRefresh: () => void;
}) {
  const setFromDashboard = useTopologyStore((s) => s.setFromDashboard);
  const jitterLoads = useTopologyStore((s) => s.jitterLoads);
  const simSpeed = useTopologyStore((s) => s.simSpeed);
  const visualPaused = useTopologyStore((s) => s.visualPaused);
  const agents = useTopologyStore((s) => s.agents);
  const selectAgent = useTopologyStore((s) => s.selectAgent);

  useEffect(() => {
    setFromDashboard(snapshot);
  }, [snapshot, setFromDashboard]);

  useEffect(() => {
    if (visualPaused) return;
    const interval = window.setInterval(jitterLoads, Math.max(400, 1600 / simSpeed));
    return () => window.clearInterval(interval);
  }, [jitterLoads, simSpeed, visualPaused]);

  const empty = agents.length === 0;

  return (
    <TopologyErrorBoundary>
      <div className="relative w-full h-[calc(100vh-11rem)] min-h-[420px] overflow-hidden rounded-lg border border-slate-900">
        {empty ? (
          <AwaitingTelemetry />
        ) : (
          <Canvas
            camera={{ position: [0, 16, 19], fov: 50 }}
            dpr={[1, 1.75]}
            gl={{ antialias: true, powerPreference: 'high-performance' }}
            onPointerMissed={() => selectAgent(null)}
          >
            <Suspense fallback={null}>
              <TopologyScene />
            </Suspense>
          </Canvas>
        )}
        {!empty && <Hud onRefresh={onRefresh} />}
        <div className="pointer-events-none absolute inset-0 z-30 scanlines" />
      </div>
    </TopologyErrorBoundary>
  );
}

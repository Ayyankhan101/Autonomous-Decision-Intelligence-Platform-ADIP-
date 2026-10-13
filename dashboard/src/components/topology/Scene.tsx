import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Grid, Line, OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { useTopologyStore } from '../../stores/topologyStore';
import type { TopologyAgent, TopologyEdge, TopologyIncident } from '../../types/topology';

const STATUS_EMISSIVE: Record<string, string> = {
  available: '#10b981',
  assigned: '#06b6d4',
  busy: '#f59e0b',
  offline: '#475569',
};

const PRIORITY_COLOR: Record<string, string> = {
  LOW: '#94a3b8',
  MEDIUM: '#38bdf8',
  HIGH: '#f59e0b',
  CRITICAL: '#f43f5e',
};

function AgentNode({
  agent,
  selected,
  flashing,
}: {
  agent: TopologyAgent;
  selected: boolean;
  flashing: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.MeshStandardMaterial>(null);
  const selectAgent = useTopologyStore((s) => s.selectAgent);
  const hovering = useRef(false);

  useFrame((_, delta) => {
    if (matRef.current) {
      const base = selected ? 1.6 : hovering.current ? 1.3 : 0.55 + agent.processingLoad / 200;
      const target = flashing ? 2.8 : base;
      matRef.current.emissiveIntensity += (target - matRef.current.emissiveIntensity) * 0.15;
    }
    if (meshRef.current && selected) {
      meshRef.current.rotation.y += delta * 0.8;
    }
    if (ringRef.current) {
      ringRef.current.rotation.z += delta * (selected ? 1.5 : 0.4);
      const s = selected ? 1.6 : 0;
      ringRef.current.scale.setScalar(ringRef.current.scale.x + (s - ringRef.current.scale.x) * 0.1);
    }
  });

  const color = flashing ? '#f43f5e' : STATUS_EMISSIVE[agent.status] ?? '#475569';

  return (
    <group position={agent.position}>
      <mesh
        ref={meshRef}
        onPointerOver={(e) => {
          e.stopPropagation();
          hovering.current = true;
          document.body.style.cursor = 'pointer';
        }}
        onPointerOut={() => {
          hovering.current = false;
          document.body.style.cursor = 'auto';
        }}
        onClick={(e) => {
          e.stopPropagation();
          selectAgent(agent.id);
        }}
      >
        <octahedronGeometry args={[0.55, 0]} />
        <meshStandardMaterial
          ref={matRef}
          color={color}
          emissive={color}
          emissiveIntensity={0.55}
          roughness={0.35}
          metalness={0.4}
        />
      </mesh>
      <mesh ref={ringRef} rotation={[Math.PI / 2, 0, 0]} scale={0}>
        <torusGeometry args={[0.95, 0.03, 8, 48]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.85} />
      </mesh>
    </group>
  );
}

function IncidentNode({
  incident,
  flashing,
}: {
  incident: TopologyIncident;
  flashing: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.MeshStandardMaterial>(null);

  useFrame((_, delta) => {
    if (meshRef.current) meshRef.current.rotation.y += delta * 0.6;
    if (matRef.current) {
      const target = flashing ? 3 : 0.9;
      matRef.current.emissiveIntensity += (target - matRef.current.emissiveIntensity) * 0.12;
    }
  });

  const color = flashing
    ? '#f43f5e'
    : (incident.priority && PRIORITY_COLOR[incident.priority]) || '#94a3b8';

  return (
    <mesh ref={meshRef} position={incident.position}>
      <icosahedronGeometry args={[0.3, 0]} />
      <meshStandardMaterial
        ref={matRef}
        color={color}
        emissive={color}
        emissiveIntensity={0.9}
        roughness={0.4}
        metalness={0.3}
      />
    </mesh>
  );
}

const EDGE_STATE_COLOR: Record<string, string> = {
  ACCEPTED: '#22d3ee',
  AUTO_ACCEPTED: '#22d3ee',
  PENDING_OVERRIDE: '#f59e0b',
  OVERRIDE_ACCEPTED: '#f59e0b',
  CONTENTION_ESCALATION: '#f43f5e',
  REJECTED_INPUT: '#f43f5e',
};

function AssignmentEdge({ edge, speed }: { edge: TopologyEdge; speed: number }) {
  const lineRef = useRef<THREE.Mesh>(null);
  const color = edge.priority ? (PRIORITY_COLOR[edge.priority] ?? '#64748b') : '#64748b';
  const points = [edge.from, edge.to];

  useFrame(() => {
    const obj = lineRef.current as unknown as { material?: { dashOffset?: number } } | null;
    const mat = obj?.material;
    if (mat && 'dashOffset' in mat && typeof mat.dashOffset === 'number') {
      mat.dashOffset -= 0.004 * speed;
    }
  });

  return (
      <Line
        ref={lineRef as never}
        points={points}
        color={EDGE_STATE_COLOR[edge.state ?? ''] ?? color}
        lineWidth={2.2}
        dashed
        dashSize={0.35}
        gapSize={0.25}
        transparent
        opacity={0.8}
      />
  );
}

export function TopologyScene() {
  const agents = useTopologyStore((s) => s.agents);
  const incidents = useTopologyStore((s) => s.incidents);
  const edges = useTopologyStore((s) => s.edges);
  const selectedAgentId = useTopologyStore((s) => s.selectedAgentId);
  const anomalyFlashId = useTopologyStore((s) => s.anomalyFlashId);
  const simSpeed = useTopologyStore((s) => s.simSpeed);
  const setFps = useTopologyStore((s) => s.setFps);
  const frames = useRef(0);
  const acc = useRef(0);

  useFrame((_, delta) => {
    frames.current += 1;
    acc.current += delta;
    if (acc.current >= 0.5) {
      setFps(Math.round(frames.current / acc.current));
      frames.current = 0;
      acc.current = 0;
    }
  });

  return (
    <>
      <color attach="background" args={['#0b0f19']} />
      <fog attach="fog" args={['#0b0f19', 28, 70]} />
      <ambientLight intensity={0.35} />
      <pointLight position={[0, 18, 0]} intensity={90} color="#22d3ee" />
      <pointLight position={[-12, 8, 10]} intensity={30} color="#6366f1" />

      <Grid
        args={[40, 40]}
        cellSize={1.5}
        cellColor="#1e3a5f"
        sectionSize={7.5}
        sectionColor="#0ea5e9"
        fadeDistance={55}
        fadeStrength={2}
        infiniteGrid
        position={[0, -0.02, 0]}
      />

      {edges.map((e) => (
        <AssignmentEdge key={e.key} edge={e} speed={simSpeed} />
      ))}

      {agents.map((a) => (
        <AgentNode
          key={a.id}
          agent={a}
          selected={a.id === selectedAgentId}
          flashing={anomalyFlashId != null && a.currentTask?.includes(anomalyFlashId) === true}
        />
      ))}

      {incidents.map((i) => (
        <IncidentNode key={i.id} incident={i} flashing={anomalyFlashId === i.id} />
      ))}

      <OrbitControls
        enableDamping
        dampingFactor={0.08}
        minDistance={6}
        maxDistance={40}
        maxPolarAngle={Math.PI / 2.1}
        makeDefault
        target={[0, 0.5, 0]}
      />
    </>
  );
}

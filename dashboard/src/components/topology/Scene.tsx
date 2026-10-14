import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { ContactShadows, Html, Line, OrbitControls, Stars } from '@react-three/drei';
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { Grid } from '@react-three/drei';
import { useTopologyStore } from '../../stores/topologyStore';
import { ZoneFloor } from './ZoneFloor';
import type { TopologyAgent, TopologyEdge, TopologyIncident } from '../../types/topology';
import type { ResourceType } from '../../types/api';
import { DECISION_STATE_THEME, PRIORITY_COLOR } from './theme';

const STATUS_EMISSIVE: Record<string, string> = {
  available: '#10b981',
  assigned: '#06b6d4',
  busy: '#f59e0b',
  offline: '#475569',
};



const TYPE_GEOMETRY: Record<ResourceType, 'capsule' | 'box' | 'dodeca' | 'torus' | 'cylinder'> = {
  ambulance: 'capsule',
  fire_truck: 'box',
  police_unit: 'dodeca',
  flood_response_unit: 'torus',
  traffic_management_unit: 'cylinder',
};

function BloomRig() {
  const { gl, scene, camera, size } = useThree();
  const composer = useMemo(() => {
    const c = new EffectComposer(gl);
    c.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(
      new THREE.Vector2(1, 1),
      0.85,
      0.45,
      0.18,
    );
    c.addPass(bloom);
    return c;
  }, [gl, scene, camera]);

  useEffect(() => {
    composer.setSize(size.width, size.height);
    composer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
  }, [composer, size]);

  useEffect(() => () => composer.dispose(), [composer]);

  useFrame(() => {
    composer.render();
  }, 1);

  return null;
}

function UnitGeometry({ type }: { type: ResourceType }) {
  switch (TYPE_GEOMETRY[type]) {
    case 'capsule':
      return <capsuleGeometry args={[0.22, 0.5, 4, 10]} />;
    case 'box':
      return <boxGeometry args={[0.7, 0.38, 0.45]} />;
    case 'dodeca':
      return <dodecahedronGeometry args={[0.42, 0]} />;
    case 'torus':
      return <torusGeometry args={[0.3, 0.12, 8, 20]} />;
    case 'cylinder':
      return <cylinderGeometry args={[0.26, 0.26, 0.55, 8]} />;
  }
}

function hashPhase(key: string): number {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
  return ((h >>> 0) % 1000) / 1000;
}

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
  const groupRef = useRef<THREE.Group>(null);
  const selectAgent = useTopologyStore((s) => s.selectAgent);
  const hovering = useRef(false);
  const phase = useMemo(() => hashPhase(agent.id) * Math.PI * 2, [agent.id]);

  useFrame((state, delta) => {
    if (groupRef.current) {
      groupRef.current.position.y =
        agent.position[1] + Math.sin(state.clock.elapsedTime * 1.4 + phase) * 0.08;
    }
    if (matRef.current) {
      const pulse =
        agent.status === 'busy'
          ? Math.sin(state.clock.elapsedTime * 4 + phase) * 0.35
          : agent.status === 'offline'
            ? Math.sin(state.clock.elapsedTime * 0.8 + phase) * 0.15
            : 0;
      const base = selected ? 1.8 : hovering.current ? 1.4 : 0.7 + agent.processingLoad / 180;
      const target = flashing ? 3.2 : base + pulse;
      matRef.current.emissiveIntensity += (target - matRef.current.emissiveIntensity) * 0.18;
    }
    if (meshRef.current && selected) {
      meshRef.current.rotation.y += delta * 0.9;
    }
    if (ringRef.current) {
      ringRef.current.rotation.z += delta * (selected ? 1.8 : 0.5);
      const s = selected ? 1.7 : 0;
      ringRef.current.scale.setScalar(ringRef.current.scale.x + (s - ringRef.current.scale.x) * 0.12);
    }
  });

  const color = flashing ? '#f43f5e' : (STATUS_EMISSIVE[agent.status] ?? '#475569');

  return (
    <group ref={groupRef} position={agent.position}>
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
        <UnitGeometry type={agent.type} />
        <meshStandardMaterial
          ref={matRef}
          color={color}
          emissive={color}
          emissiveIntensity={0.7}
          roughness={0.3}
          metalness={0.5}
        />
      </mesh>
      {agent.status === 'assigned' || agent.status === 'busy' ? (
        <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0.45, 0]}>
          <torusGeometry args={[0.18, 0.035, 6, 16]} />
          <meshBasicMaterial color="#22d3ee" transparent opacity={0.9} />
        </mesh>
      ) : null}
      <mesh ref={ringRef} rotation={[Math.PI / 2, 0, 0]} scale={0}>
        <torusGeometry args={[1.0, 0.035, 8, 48]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.9} />
      </mesh>
      {selected ? (
        <Html position={[0, 1.25, 0]} center distanceFactor={14} zIndexRange={[30, 0]}>
          <div className="pointer-events-none whitespace-nowrap bg-slate-950/90 border border-cyan-400/60 rounded px-2 py-1 font-mono text-[10px] text-cyan-200 shadow-[0_0_12px_rgba(34,211,238,0.35)]">
            {agent.id} · {agent.status.toUpperCase()} · {Math.round(agent.processingLoad)}%
          </div>
        </Html>
      ) : null}
    </group>
  );
}

function Shockwave({ color }: { color: string }) {
  const ref = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.MeshBasicMaterial>(null);
  useFrame((_, delta) => {
    if (!ref.current || !matRef.current) return;
    const s = ref.current.scale.x + delta * 3.5;
    ref.current.scale.setScalar(s);
    matRef.current.opacity = Math.max(0, 0.7 - (s - 1) * 0.35);
  });
  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
      <ringGeometry args={[0.75, 0.85, 48]} />
      <meshBasicMaterial ref={matRef} color={color} transparent opacity={0.7} side={THREE.DoubleSide} />
    </mesh>
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
  const sirenA = useRef<THREE.Mesh>(null);
  const sirenB = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.MeshStandardMaterial>(null);

  useFrame((state, delta) => {
    if (meshRef.current) meshRef.current.rotation.y += delta * 0.8;
    if (matRef.current) {
      const target = flashing ? 3.4 : 1.2 + Math.sin(state.clock.elapsedTime * 3) * 0.25;
      matRef.current.emissiveIntensity += (target - matRef.current.emissiveIntensity) * 0.14;
    }
    if (sirenA.current && sirenB.current) {
      sirenA.current.rotation.y += delta * 3;
      sirenB.current.rotation.y += delta * 3;
    }
  });

  const color = flashing
    ? '#f43f5e'
    : (incident.priority && PRIORITY_COLOR[incident.priority]) || '#94a3b8';

  return (
    <group position={incident.position}>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[0.32, 0]} />
        <meshStandardMaterial
          ref={matRef}
          color={color}
          emissive={color}
          emissiveIntensity={1.2}
          roughness={0.35}
          metalness={0.35}
        />
      </mesh>
      <mesh ref={sirenA} position={[0.45, 0.15, 0]}>
        <sphereGeometry args={[0.07, 8, 8]} />
        <meshBasicMaterial color="#f43f5e" />
      </mesh>
      <mesh ref={sirenB} position={[-0.45, 0.15, 0]}>
        <sphereGeometry args={[0.07, 8, 8]} />
        <meshBasicMaterial color="#38bdf8" />
      </mesh>
      {flashing ? <Shockwave color="#f43f5e" /> : null}
    </group>
  );
}



function AssignmentEdge({ edge, speed }: { edge: TopologyEdge; speed: number }) {
  const lineRef = useRef<THREE.Mesh>(null);
  const pulseRef = useRef<THREE.Mesh>(null);
  const tRef = useRef(hashPhase(edge.key));
  const color = edge.priority ? (PRIORITY_COLOR[edge.priority] ?? '#64748b') : '#64748b';
  const lineColor = DECISION_STATE_THEME[edge.state ?? 'AUTO_APPROVED'].color ?? color;
  const points = useMemo(
    () => [new THREE.Vector3(...edge.from), new THREE.Vector3(...edge.to)],
    [edge.from, edge.to],
  );

  useFrame((_, delta) => {
    const obj = lineRef.current as unknown as { material?: { dashOffset?: number } } | null;
    const mat = obj?.material;
    if (mat && 'dashOffset' in mat && typeof mat.dashOffset === 'number') {
      mat.dashOffset -= 0.005 * speed;
    }
    if (pulseRef.current) {
      tRef.current = (tRef.current + delta * 0.35 * speed) % 1;
      pulseRef.current.position.lerpVectors(points[0], points[1], tRef.current);
      pulseRef.current.position.y += 0.12;
    }
  });

  return (
    <group>
      <Line
        ref={lineRef as never}
        points={points}
        color={lineColor}
        lineWidth={2.4}
        dashed
        dashSize={0.4}
        gapSize={0.22}
        transparent
        opacity={0.85}
      />
      <mesh ref={pulseRef}>
        <sphereGeometry args={[0.09, 8, 8]} />
        <meshBasicMaterial color={lineColor} />
      </mesh>
    </group>
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
      <color attach="background" args={['#070b14']} />
      <fog attach="fog" args={['#070b14', 30, 75]} />
      <ambientLight intensity={0.4} />
      <pointLight position={[0, 20, 0]} intensity={110} color="#22d3ee" />
      <pointLight position={[-14, 10, 12]} intensity={40} color="#6366f1" />
      <pointLight position={[12, 8, -10]} intensity={25} color="#f43f5e" />

      <Stars radius={80} depth={40} count={2500} factor={3} saturation={0} fade speed={0.6} />
      <Grid
        infiniteGrid
        fadeDistance={50}
        fadeStrength={0.5}
        cellSize={10}
        sectionSize={120}
        uniform-grid-color="#22d3ee"
        uniform-grid-color-dim="#0d1321"
      />
      <ZoneFloor />

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

      <ContactShadows
        position={[0, -0.05, 0]}
        opacity={0.55}
        scale={60}
        blur={2.2}
        far={12}
        color="#000000"
      />

      <OrbitControls
        enableDamping
        dampingFactor={0.08}
        minDistance={6}
        maxDistance={45}
        maxPolarAngle={Math.PI / 2.1}
        makeDefault
        target={[0, 0.5, 0]}
        autoRotate={selectedAgentId == null}
        autoRotateSpeed={0.35}
      />

      <BloomRig />
    </>
  );
}

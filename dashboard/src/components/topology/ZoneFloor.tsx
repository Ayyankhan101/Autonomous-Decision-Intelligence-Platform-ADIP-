import { useMemo } from 'react';
import * as THREE from 'three';
import { Line, Text } from '@react-three/drei';
import { ZONE_GEO } from '../../data/peshawarZones';
import { projectToScene } from '../../stores/topologyStore';
import type { Zone } from '../../types/api';

const ZONE_TINT: Record<Zone, { fill: string; edge: string }> = {
  central: { fill: '#0ea5e9', edge: '#22d3ee' },
  north: { fill: '#10b981', edge: '#34d399' },
  south: { fill: '#8b5cf6', edge: '#a78bfa' },
  east: { fill: '#f59e0b', edge: '#fbbf24' },
  west: { fill: '#f43f5e', edge: '#fb7185' },
};

function projectPolygon(polygon: [number, number][]): [number, number][] {
  return polygon.map(([lat, lon]) => {
    const [x, , z] = projectToScene(lat, lon);
    return [x, -z];
  });
}

function ZonePlate({
  id,
  name,
  polygon,
}: {
  id: Zone;
  name: string;
  polygon: [number, number][];
}) {
  const tint = ZONE_TINT[id];

  const { shape, edgePoints } = useMemo(() => {
    const pts = projectPolygon(polygon);
    const shape = new THREE.Shape();
    pts.forEach(([x, y], i) => {
      if (i === 0) shape.moveTo(x, y);
      else shape.lineTo(x, y);
    });
    shape.closePath();
    const edgePoints: [number, number, number][] = pts.map(([x, y]) => [x, 0.01, -y]);
    edgePoints.push([pts[0][0], 0.01, -pts[0][1]]);
    return { shape, edgePoints };
  }, [polygon]);

  const centroid = useMemo(() => {
    const pts = projectPolygon(polygon);
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    return [cx, 0.01, -cy] as [number, number, number];
  }, [polygon]);

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]}>
        <shapeGeometry args={[shape]} />
        <meshBasicMaterial
          color={tint.fill}
          transparent
          opacity={0.06}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
      <Line points={edgePoints} color={tint.edge} lineWidth={1.6} transparent opacity={0.55} />
      <Text
        position={centroid}
        rotation={[-Math.PI / 2.4, 0, 0]}
        fontSize={0.55}
        color={tint.edge}
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.02}
        outlineColor="#0b0f19"
        fillOpacity={0.75}
      >
        {name.toUpperCase()}
      </Text>
    </group>
  );
}

export function ZoneFloor() {
  return (
    <group>
      {ZONE_GEO.map((z) => (
        <ZonePlate key={z.id} id={z.id} name={z.name} polygon={z.polygon} />
      ))}
    </group>
  );
}

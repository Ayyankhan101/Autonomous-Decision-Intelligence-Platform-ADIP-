import React, { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Polygon, Polyline, Marker } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type {
  DecisionRecord,
  IncidentRecord,
  Priority,
  Resource,
  ResourceType,
  Zone,
} from '../types/api';
import { ZONE_GEO, PESHAWAR_CENTER, jitteredPosition } from '../data/peshawarZones';

interface PeshawarMapProps {
  incidents: IncidentRecord[];
  decisions: DecisionRecord[];
  resources: Resource[];
  selectedIncidentId: string | null;
  onSelectIncident: (id: string) => void;
  newIncidentIds?: string[];
}

const INCIDENT_COLORS: Record<Priority, string> = {
  CRITICAL: '#f87171',
  HIGH: '#fbbf24',
  MEDIUM: '#facc15',
  LOW: '#60a5fa',
};

const STATE_COLORS: Record<string, string> = {
  OVERRIDE_ACTIVE: '#22d3ee',
  HOLD_FOR_HUMAN: '#c084fc',
  CONTENTION_ESCALATION: '#fb7185',
  MODEL_DEGRADED: '#fb923c',
  REJECTED_INPUT: '#94a3b8',
};

const UNIT_COLORS: Record<string, string> = {
  available: '#34d399',
  assigned: '#22d3ee',
  busy: '#fbbf24',
  offline: '#64748b',
};

const UNIT_SHAPES: Record<ResourceType, string> = {
  ambulance: '▲',
  fire_truck: '■',
  police_unit: '●',
  flood_response_unit: '◆',
  traffic_management_unit: '▬',
};

function priorityColor(priority?: Priority, state?: string): string {
  if (state && STATE_COLORS[state]) return STATE_COLORS[state];
  return priority ? INCIDENT_COLORS[priority] : '#94a3b8';
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function incidentIcon(inc: IncidentRecord, decision: DecisionRecord | undefined, isNew: boolean, selected: boolean): L.DivIcon {
  const color = priorityColor(decision?.priority, decision?.state);
  const ring = selected
    ? 'box-shadow:0 0 0 3px rgba(99,102,241,.8), 0 0 12px rgba(99,102,241,.5);'
    : isNew
      ? 'box-shadow:0 0 0 2px rgba(34,211,238,.9), 0 0 14px rgba(34,211,238,.6);'
      : 'box-shadow:0 0 8px ' + color + '66;';
  const pulse = decision?.priority === 'CRITICAL' ? 'animation:jev-pulse 1.4s ease-in-out infinite;' : '';
  return L.divIcon({
    className: '',
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    html: `<div title="${escapeHtml(inc.incident_id)}" style="width:18px;height:18px;border-radius:9999px;background:${color};border:2px solid #0b0f19;${ring}${pulse}"></div>`,
  });
}

function unitIcon(res: Resource): L.DivIcon {
  const color = UNIT_COLORS[res.status] ?? '#94a3b8';
  const shape = UNIT_SHAPES[res.type] ?? '■';
  return L.divIcon({
    className: '',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    html: `<div title="${escapeHtml(res.resource_id)}" style="width:14px;height:14px;display:flex;align-items:center;justify-content:center;color:${color};font-size:11px;line-height:1;text-shadow:0 0 6px ${color};background:#0b0f19cc;border:1px solid ${color}55;border-radius:3px;">${shape}</div>`,
  });
}

interface FlightLine {
  key: string;
  positions: [number, number][];
}

export const PeshawarMap: React.FC<PeshawarMapProps> = ({
  incidents,
  decisions,
  resources,
  selectedIncidentId,
  onSelectIncident,
  newIncidentIds,
}) => {
  const prevAssignRef = React.useRef<Map<string, string>>(new Map());
  const [flights, setFlights] = React.useState<FlightLine[]>([]);

  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      const current = new Map<string, string>();
      for (const d of decisions) {
        for (const unitId of d.assigned_resource_ids) {
          current.set(unitId, d.incident_id);
        }
      }
      const prev = prevAssignRef.current;
      if (prev.size > 0) {
        const newFlights: FlightLine[] = [];
        for (const [unitId, incId] of current) {
          if (prev.get(unitId) === incId) continue;
          const unit = resources.find((r) => r.resource_id === unitId);
          const inc = incidents.find((i) => i.incident_id === incId);
          if (!unit || !inc || unit.zone === inc.zone) continue;
          newFlights.push({
            key: `${unitId}-${incId}-${Date.now()}`,
            positions: [jitteredPosition(unit.zone, unitId), jitteredPosition(inc.zone, incId)],
          });
        }
        if (newFlights.length > 0) {
          setFlights((f) => [...f.slice(-3), ...newFlights]);
          for (const nf of newFlights) {
            setTimeout(() => {
              setFlights((cur) => cur.filter((x) => x.key !== nf.key));
            }, 1600);
          }
        }
      }
      prevAssignRef.current = current;
    });
    return () => cancelAnimationFrame(raf);
  }, [decisions, resources, incidents]);

  const incidentByZone = useMemo(() => {
    const m = new Map<Zone, number>();
    for (const inc of incidents) m.set(inc.zone, (m.get(inc.zone) ?? 0) + 1);
    return m;
  }, [incidents]);

  const decisionByIncident = useMemo(() => {
    const m = new Map<string, DecisionRecord>();
    for (const d of decisions) m.set(d.incident_id, d);
    return m;
  }, [decisions]);

  const zoneFill = (zoneId: Zone): { color: string; fillColor: string; weight: number; fillOpacity: number } => {
    const count = incidentByZone.get(zoneId) ?? 0;
    const fillColor = count >= 3 ? '#7f1d1d' : count === 2 ? '#78350f' : count === 1 ? '#164e63' : '#1e293b';
    return { color: '#334155', fillColor, weight: 1.2, fillOpacity: 0.45 };
  };

  return (
    <MapContainer
      center={PESHAWAR_CENTER}
      zoom={12}
      minZoom={11}
      maxZoom={16}
      className="h-full w-full rounded-lg z-0"
      style={{ background: '#0b0f19' }}
      attributionControl
      zoomControl
    >
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        maxZoom={19}
        className="jev-dark-tiles"
      />
      {ZONE_GEO.map((z) => (
        <Polygon key={z.id} positions={z.polygon} pathOptions={zoneFill(z.id)} />
      ))}
      {ZONE_GEO.map((z) => (
        <Marker
          key={`label-${z.id}`}
          position={z.centroid}
          interactive={false}
          icon={L.divIcon({
            className: '',
            iconSize: [120, 28],
            iconAnchor: [60, 14],
            html: `<div style="text-align:center;pointer-events:none;"><div style="font:600 10px 'JetBrains Mono',monospace;color:#94a3b8;text-shadow:0 1px 3px #000;letter-spacing:.05em;text-transform:uppercase;">${z.name}</div><div style="font:400 9px 'JetBrains Mono',monospace;color:#64748b;text-shadow:0 1px 3px #000;">${(incidentByZone.get(z.id) ?? 0)} inc</div></div>`,
          })}
        />
      ))}
      {flights.map((f) => (
        <Polyline
          key={f.key}
          positions={f.positions}
          pathOptions={{ color: '#22d3ee', weight: 2, dashArray: '6 8', opacity: 0.9 }}
        />
      ))}
      {resources.map((r) => (
        <Marker
          key={r.resource_id}
          position={jitteredPosition(r.zone, r.resource_id, 0.006)}
          icon={unitIcon(r)}
          zIndexOffset={-100}
        />
      ))}
      {incidents.map((inc) => (
        <Marker
          key={inc.incident_id}
          position={jitteredPosition(inc.zone, inc.incident_id)}
          icon={incidentIcon(
            inc,
            decisionByIncident.get(inc.incident_id),
            newIncidentIds?.includes(inc.incident_id) ?? false,
            inc.incident_id === selectedIncidentId,
          )}
          eventHandlers={{ click: () => onSelectIncident(inc.incident_id) }}
          zIndexOffset={100}
        />
      ))}
    </MapContainer>
  );
};

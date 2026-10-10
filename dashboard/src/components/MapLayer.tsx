import React from 'react';
import {
  AlertCircle,
  Car,
  Flame,
  LifeBuoy,
  MapPin,
  Navigation,
  Shield,
  Siren,
  Truck,
  Wind,
} from 'lucide-react';
import type {
  DecisionRecord,
  IncidentRecord,
  IncidentType,
  Priority,
  Resource,
  ResourceType,
  Zone,
} from '../types/api';

interface MapLayerProps {
  incidents: IncidentRecord[];
  decisions: DecisionRecord[];
  resources: Resource[];
  selectedIncidentId: string | null;
  onSelectIncident: (id: string) => void;
  newIncidentIds?: string[];
}

const ZONES: { id: Zone; name: string; description: string; colSpan: string }[] = [
  { id: 'north', name: 'North Sector', description: 'Residential & Light Industrial', colSpan: 'col-span-1' },
  { id: 'central', name: 'Central Core', description: 'High-Density Commercial & Financial', colSpan: 'col-span-1' },
  { id: 'east', name: 'East Corridor', description: 'Major Transit Artery & Logistics', colSpan: 'col-span-1' },
  { id: 'south', name: 'South District', description: 'Port Facilities & Heavy Industry', colSpan: 'col-span-1' },
  { id: 'west', name: 'West Sector', description: 'Suburban & Reservoir Zone', colSpan: 'col-span-1' },
];

interface Flight {
  key: string;
  unitId: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
}

const FlightPill: React.FC<{
  flight: Flight;
  onDone: (key: string) => void;
}> = ({ flight, onDone }) => {
  const [pos, setPos] = React.useState(flight.from);
  React.useEffect(() => {
    const raf = requestAnimationFrame(() => setPos(flight.to));
    const t = setTimeout(() => onDone(flight.key), 1500);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="absolute z-30 -translate-x-1/2 -translate-y-1/2 px-2 py-0.5 rounded-full bg-cyan-950/95 border border-cyan-400/70 text-[10px] font-mono font-bold text-cyan-100 shadow-lg shadow-cyan-950/60 flex items-center gap-1 whitespace-nowrap pointer-events-none"
      style={{
        left: pos.x,
        top: pos.y,
        transition: 'left 1.2s ease-in-out, top 1.2s ease-in-out',
      }}
    >
      <Navigation className="w-2.5 h-2.5" />
      <span>{flight.unitId}</span>
    </div>
  );
};

export const MapLayer: React.FC<MapLayerProps> = ({
  incidents,
  decisions,
  resources,
  selectedIncidentId,
  onSelectIncident,
  newIncidentIds,
}) => {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const zoneRefs = React.useRef<Partial<Record<Zone, HTMLDivElement | null>>>({});
  const prevAssignRef = React.useRef<Map<string, string>>(new Map());
  const [flights, setFlights] = React.useState<Flight[]>([]);

  // Dispatch animation: detect newly assigned units and fly them from their
  // home zone card to the incident zone card (skips same-zone assignments).
  // Deferred via rAF so rects are post-layout and setState isn't synchronous.
  React.useEffect(() => {
    const raf = requestAnimationFrame(() => {
      const current = new Map<string, string>();
      for (const d of decisions) {
        for (const unitId of d.assigned_resource_ids) {
          current.set(unitId, d.incident_id);
        }
      }
      const prev = prevAssignRef.current;
      const container = containerRef.current;
      if (container && prev.size > 0) {
        const newFlights: Flight[] = [];
        for (const [unitId, incId] of current) {
          if (prev.get(unitId) === incId) continue;
          const unit = resources.find((r) => r.resource_id === unitId);
          const inc = incidents.find((i) => i.incident_id === incId);
          if (!unit || !inc || unit.zone === inc.zone) continue;
          const fromEl = zoneRefs.current[unit.zone];
          const toEl = zoneRefs.current[inc.zone];
          if (!fromEl || !toEl) continue;
          const cRect = container.getBoundingClientRect();
          const fRect = fromEl.getBoundingClientRect();
          const tRect = toEl.getBoundingClientRect();
          newFlights.push({
            key: `${unitId}-${incId}-${Date.now()}`,
            unitId,
            from: {
              x: fRect.left - cRect.left + fRect.width / 2,
              y: fRect.top - cRect.top + 28,
            },
            to: {
              x: tRect.left - cRect.left + tRect.width / 2,
              y: tRect.top - cRect.top + 28,
            },
          });
        }
        if (newFlights.length > 0) {
          setFlights((f) => [...f.slice(-4), ...newFlights]);
        }
      }
      prevAssignRef.current = current;
    });
    return () => cancelAnimationFrame(raf);
  }, [decisions, resources, incidents]);

  const removeFlight = React.useCallback((key: string) => {
    setFlights((f) => f.filter((x) => x.key !== key));
  }, []);
  const getDecisionForIncident = (incId: string): DecisionRecord | undefined => {
    const list = decisions.filter((d) => d.incident_id === incId);
    return list.length > 0 ? list[list.length - 1] : undefined;
  };

  const getPriorityBadgeClass = (priority?: Priority, state?: string) => {
    if (state === 'OVERRIDE_ACTIVE') {
      return 'bg-cyan-950 text-cyan-300 border-cyan-500/50 shadow-cyan-950/50 ring-1 ring-cyan-500/40';
    }
    if (state === 'REJECTED_INPUT') {
      return 'bg-slate-900 text-slate-400 border-slate-700';
    }
    if (state === 'HOLD_FOR_HUMAN') {
      return 'bg-purple-950 text-purple-300 border-purple-500/50 animate-pulse';
    }
    switch (priority) {
      case 'CRITICAL':
        return 'bg-red-950 text-red-200 border-red-500/60 shadow-red-950/50 animate-pulse';
      case 'HIGH':
        return 'bg-amber-950 text-amber-300 border-amber-500/50';
      case 'MEDIUM':
        return 'bg-yellow-950 text-yellow-300 border-yellow-500/40';
      case 'LOW':
        return 'bg-blue-950 text-blue-300 border-blue-500/40';
      default:
        return 'bg-slate-900 text-slate-300 border-slate-700';
    }
  };

  const getIncidentIcon = (type: IncidentType) => {
    switch (type) {
      case 'fire':
        return <Flame className="w-4 h-4 text-orange-400" />;
      case 'accident':
        return <Car className="w-4 h-4 text-amber-400" />;
      case 'flood':
        return <Wind className="w-4 h-4 text-cyan-400" />;
      case 'traffic_spike':
        return <AlertCircle className="w-4 h-4 text-yellow-400" />;
      default:
        return <AlertCircle className="w-4 h-4 text-indigo-400" />;
    }
  };

  const getResourceIcon = (type: ResourceType) => {
    switch (type) {
      case 'ambulance':
        return <LifeBuoy className="w-3.5 h-3.5 text-rose-400" />;
      case 'fire_truck':
        return <Flame className="w-3.5 h-3.5 text-orange-400" />;
      case 'police_unit':
        return <Shield className="w-3.5 h-3.5 text-blue-400" />;
      case 'flood_response_unit':
        return <Wind className="w-3.5 h-3.5 text-cyan-400" />;
      case 'traffic_management_unit':
        return <Truck className="w-3.5 h-3.5 text-yellow-400" />;
    }
  };

  // Group resources by type & calculate available vs total
  const resourceSummary = React.useMemo(() => {
    const summary: Record<ResourceType, { total: number; available: number }> = {
      ambulance: { total: 0, available: 0 },
      fire_truck: { total: 0, available: 0 },
      police_unit: { total: 0, available: 0 },
      flood_response_unit: { total: 0, available: 0 },
      traffic_management_unit: { total: 0, available: 0 },
    };

    resources.forEach((r) => {
      if (summary[r.type]) {
        summary[r.type].total += 1;
        if (r.status === 'available') {
          summary[r.type].available += 1;
        }
      }
    });

    return summary;
  }, [resources]);

  return (
    <div className="flex flex-col gap-4">
      {/* Fleet Resource Bar */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 shadow-md">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Siren className="w-4 h-4 text-indigo-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Fleet Resource Deployment Pool
            </h3>
          </div>
          <span className="text-xs text-slate-500 font-mono">
            Total Units: {resources.length}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
          {(Object.entries(resourceSummary) as [ResourceType, { total: number; available: number }][]).map(
            ([type, counts]) => {
              const inUse = counts.total - counts.available;
              const pct = counts.total > 0 ? (counts.available / counts.total) * 100 : 0;
              return (
                <div
                  key={type}
                  className="bg-slate-950/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-1.5">
                      {getResourceIcon(type)}
                      <span className="text-xs font-semibold capitalize text-slate-200">
                        {type.replaceAll('_', ' ')}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                        counts.available > 0
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/40'
                          : 'bg-red-950 text-red-300 border border-red-800/40'
                      }`}
                    >
                      {counts.available} / {counts.total}
                    </span>
                  </div>

                  {/* Utilization bar */}
                  <div className="w-full bg-slate-800/80 h-1.5 rounded-full overflow-hidden mt-1">
                    <div
                      className={`h-full transition-all duration-500 ${
                        pct > 50 ? 'bg-emerald-500' : pct > 20 ? 'bg-amber-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <div className="flex justify-between items-center text-[10px] text-slate-500 mt-1 font-mono">
                    <span>Avail: {counts.available}</span>
                    <span>Dispatched: {inUse}</span>
                  </div>
                </div>
              );
            }
          )}
        </div>
      </div>

      {/* Urban Map / 5-Zone Matrix */}
      <div
        ref={containerRef}
        className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-md relative"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              City Surveillance & Incident Zones
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            {incidents.length} active registered incident{incidents.length === 1 ? '' : 's'}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {ZONES.map((zone) => {
            const zoneIncidents = incidents.filter((i) => i.zone === zone.id);
            const zoneResources = resources.filter((r) => r.zone === zone.id);
            const availableInZone = zoneResources.filter((r) => r.status === 'available').length;

            return (
              <div
                key={zone.id}
                ref={(el) => {
                  zoneRefs.current[zone.id] = el;
                }}
                className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3.5 flex flex-col justify-between transition-all hover:border-slate-700 relative overflow-hidden group"
              >
                {/* Zone Header */}
                <div className="flex items-center justify-between border-b border-slate-800/60 pb-2 mb-2.5">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-sm shadow-cyan-400" />
                      <h4 className="text-sm font-bold text-slate-100">{zone.name}</h4>
                    </div>
                    <p className="text-[11px] text-slate-500">{zone.description}</p>
                  </div>
                  <div className="text-right">
                    <span className="text-[11px] font-mono text-slate-400">
                      Units: <strong className="text-emerald-400">{availableInZone}</strong> / {zoneResources.length}
                    </span>
                  </div>
                </div>

                {/* Zone Incident Cards */}
                <div className="flex-1 space-y-2 min-h-[110px] max-h-[220px] overflow-y-auto pr-1">
                  {zoneIncidents.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-xs text-slate-600 font-mono py-6">
                      No active incidents in this zone
                    </div>
                  ) : (
                    zoneIncidents.map((incident) => {
                      const dec = getDecisionForIncident(incident.incident_id);
                      const isSelected = incident.incident_id === selectedIncidentId;
                      const isNew = newIncidentIds?.includes(incident.incident_id) ?? false;
                      const priority = dec?.priority;
                      const state = dec?.state;

                      return (
                        <div
                          key={incident.incident_id}
                          onClick={() => onSelectIncident(incident.incident_id)}
                          className={`p-2.5 rounded-lg border cursor-pointer transition-all flex items-center justify-between gap-3 ${
                            isSelected
                              ? 'bg-indigo-950/40 border-indigo-500 shadow-md shadow-indigo-950/50 ring-1 ring-indigo-500/50'
                              : isNew
                                ? 'bg-slate-900/60 border-cyan-400/70 ring-1 ring-cyan-400/40 shadow-[0_0_10px_rgba(34,211,238,0.25)]'
                                : 'bg-slate-900/60 border-slate-800/80 hover:bg-slate-800/60 hover:border-slate-700'
                          }`}
                        >
                          <div className="flex items-center gap-2.5 min-w-0">
                            <div className="p-1.5 rounded-md bg-slate-950 border border-slate-800">
                              {getIncidentIcon(incident.incident_type)}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs font-bold text-slate-200 truncate">
                                  {incident.incident_id}
                                </span>
                                <span className="text-[10px] uppercase font-mono text-slate-500">
                                  {incident.incident_type.replaceAll('_', ' ')}
                                </span>
                              </div>
                              <div className="flex items-center gap-2 text-[10px] text-slate-400 mt-0.5 font-mono">
                                <span>Reps: {incident.report_count}</span>
                                <span>•</span>
                                <span>Units: {incident.assigned_resource_ids.length}</span>
                              </div>
                            </div>
                          </div>

                          <div className="flex flex-col items-end gap-1">
                            <span
                              className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${getPriorityBadgeClass(
                                priority,
                                state
                              )}`}
                            >
                              {state === 'OVERRIDE_ACTIVE'
                                ? 'OVERRIDE'
                                : state === 'HOLD_FOR_HUMAN'
                                ? 'HOLD'
                                : priority || 'PENDING'}
                            </span>
                            {isNew && (
                              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/50 animate-pulse">
                                NEW
                              </span>
                            )}
                            {state && (
                              <span className="text-[9px] font-mono text-slate-500">
                                {state}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Dispatch flight overlay — units crossing the city in real time */}
        {flights.map((f) => (
          <FlightPill key={f.key} flight={f} onDone={removeFlight} />
        ))}
      </div>
    </div>
  );
};

import React from 'react';
import {
  Flame,
  LifeBuoy,
  MapPin,
  Shield,
  Siren,
  Truck,
  Wind,
} from 'lucide-react';
import type {
  DecisionRecord,
  IncidentRecord,
  Resource,
  ResourceType,
} from '../types/api';
import { PeshawarMap } from './PeshawarMap';

interface MapLayerProps {
  incidents: IncidentRecord[];
  decisions: DecisionRecord[];
  resources: Resource[];
  selectedIncidentId: string | null;
  onSelectIncident: (id: string) => void;
  newIncidentIds?: string[];
}

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

export const MapLayer: React.FC<MapLayerProps> = ({
  incidents,
  decisions,
  resources,
  selectedIncidentId,
  onSelectIncident,
  newIncidentIds,
}) => {
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

      {/* Live Map — Peshawar zones, units, incidents */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-md relative">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              City Surveillance & Incident Zones — Peshawar
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            {incidents.length} active registered incident{incidents.length === 1 ? '' : 's'}
          </span>
        </div>

        <div className="h-[420px] xl:h-[520px] rounded-lg overflow-hidden border border-slate-800">
          <PeshawarMap
            incidents={incidents}
            decisions={decisions}
            resources={resources}
            selectedIncidentId={selectedIncidentId}
            onSelectIncident={onSelectIncident}
            newIncidentIds={newIncidentIds}
          />
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2.5 text-[10px] font-mono text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-cyan-400" />
            incident (size/color = priority, click to inspect)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block text-emerald-400">▲</span> ambulance
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block text-orange-400">■</span> fire
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block text-blue-400">●</span> police
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block text-cyan-400">◆</span> flood
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block text-yellow-400">▬</span> traffic
          </span>
          <span className="ml-auto text-slate-600">tiles © OpenStreetMap contributors</span>
        </div>
      </div>
    </div>
  );
};

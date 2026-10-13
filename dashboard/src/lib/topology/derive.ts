import { PESHAWAR_CENTER } from '../../data/peshawarZones';
import type { Resource } from '../../types/api';

export function projectToScene(lat: number, lon: number): [number, number, number] {
  const LAT_SCALE = 95;
  const LON_SCALE = 95;
  const [clat, clon] = PESHAWAR_CENTER;
  return [(lon - clon) * LON_SCALE, 0, -(lat - clat) * LAT_SCALE];
}

export function deriveFleetUtilisation(resources: Resource[]): number {
  const nonOffline = resources.filter((r) => r.status !== 'offline').length;
  if (nonOffline === 0) return 0;
  const assignedBusy = resources.filter(
    (r) => r.status !== 'available' && r.status !== 'offline',
  ).length;
  return Math.round((assignedBusy / nonOffline) * 100);
}

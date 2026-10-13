export function projectToScene(lat: number, lon: number): [number, number, number] {
  const LAT_SCALE = 95;
  const LON_SCALE = 95;
  const [clat, clon] = [0, 0]; // placeholder; actual centre computed per use
  return [(lon - clon) * LON_SCALE, 0, -(lat - clat) * LAT_SCALE];
}

export function deriveFleetUtilisation(agents: any[]): number {
  const nonOffline = agents.filter((a: any) => a.status !== 'offline').length;
  if (nonOffline === 0) return 0;
  const assignedBusy = agents.filter((a: any) => a.status !== 'available' && a.status !== 'offline').length;
  return Math.round((assignedBusy / nonOffline) * 100);
}
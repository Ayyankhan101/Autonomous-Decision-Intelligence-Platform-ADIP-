import type { Zone } from '../types/api';

export interface ZoneGeo {
  id: Zone;
  name: string;
  description: string;
  polygon: [number, number][];
  centroid: [number, number];
}

export const PESHAWAR_CENTER: [number, number] = [34.008, 71.578];

export const ZONE_GEO: ZoneGeo[] = [
  {
    id: 'central',
    name: 'Central Core',
    description: 'Saddar · University Rd · Khyber Rd',
    polygon: [
      [34.02, 71.555],
      [34.022, 71.59],
      [34.005, 71.598],
      [33.995, 71.588],
      [33.992, 71.56],
      [34.005, 71.548],
    ],
    centroid: [34.007, 71.575],
  },
  {
    id: 'north',
    name: 'North Sector',
    description: 'Peshawar Cantt · Nowshera Rd',
    polygon: [
      [34.022, 71.545],
      [34.02, 71.6],
      [34.032, 71.628],
      [34.055, 71.61],
      [34.052, 71.515],
      [34.036, 71.51],
    ],
    centroid: [34.036, 71.565],
  },
  {
    id: 'south',
    name: 'South District',
    description: 'Hayatabad · Bara Rd corridor',
    polygon: [
      [33.965, 71.53],
      [33.968, 71.6],
      [33.99, 71.595],
      [33.994, 71.565],
      [33.988, 71.532],
    ],
    centroid: [33.979, 71.565],
  },
  {
    id: 'east',
    name: 'East Corridor',
    description: 'Mardan Rd · Charsadda Rd · Chamrani',
    polygon: [
      [34.028, 71.6],
      [34.034, 71.68],
      [34.0, 71.69],
      [33.99, 71.64],
      [33.995, 71.598],
      [34.018, 71.598],
    ],
    centroid: [34.01, 71.64],
  },
  {
    id: 'west',
    name: 'West Sector',
    description: 'Pabi · Shah Kas · Khyber Pass axis',
    polygon: [
      [34.04, 71.44],
      [34.048, 71.515],
      [34.022, 71.545],
      [34.005, 71.548],
      [33.992, 71.56],
      [33.988, 71.5],
      [34.01, 71.445],
    ],
    centroid: [34.015, 71.495],
  },
];

const ZONE_BY_ID = new Map(ZONE_GEO.map((z) => [z.id, z]));

export function zoneCentroid(zone: Zone): [number, number] {
  return ZONE_BY_ID.get(zone)?.centroid ?? PESHAWAR_CENTER;
}

function hashOf(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return h >>> 0;
}

export function jitteredPosition(zone: Zone, id: string, spread = 0.008): [number, number] {
  const [lat, lon] = zoneCentroid(zone);
  const h = hashOf(id);
  const dx = (((h & 0xffff) / 0xffff) - 0.5) * 2 * spread;
  const dy = ((((h >>> 16) & 0xffff) / 0xffff) - 0.5) * 2 * spread;
  return [lat + dy, lon + dx];
}

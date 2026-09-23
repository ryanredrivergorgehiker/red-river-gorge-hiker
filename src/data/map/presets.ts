export interface MapPreset {
  id: 'simple' | 'terrain' | 'route-planning' | 'land-access' | 'all-layers';
  label: string;
  baseLayerId: string;
  overlayLayerIds: string[];
  waypointMinZoom: number;
  note: string;
}
export const mapPresets: MapPreset[] = [
  { id: 'simple', label: 'Simple', baseLayerId: 'kytopo', overlayLayerIds: [], waypointMinZoom: 13, note: 'Clean route-first view.' },
  { id: 'terrain', label: 'Terrain', baseLayerId: 'kytopo', overlayLayerIds: ['ky-hillshade'], waypointMinZoom: 12, note: 'Topo plus Kentucky LiDAR-derived hillshade.' },
  { id: 'route-planning', label: 'Route Planning', baseLayerId: 'kytopo', overlayLayerIds: ['ky-hillshade'], waypointMinZoom: 12, note: 'Route, approved public waypoints, terrain, and current source links.' },
  { id: 'land-access', label: 'Land & Access', baseLayerId: 'usgs-topo', overlayLayerIds: [], waypointMinZoom: 12, note: 'Approved land-manager context only. Parcel/private-property remains disabled.' },
  { id: 'all-layers', label: 'All Layers', baseLayerId: 'ky-aerial', overlayLayerIds: ['ky-hillshade'], waypointMinZoom: 11, note: 'Aerial plus approved terrain overlay and RRGH route data.' }
];

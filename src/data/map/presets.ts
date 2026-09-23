export const mapPresets = [
  { id: 'simple', label: 'Simple', base: 'kytopo', hillshade: false, waypoints: false },
  { id: 'terrain', label: 'Terrain', base: 'kytopo', hillshade: true, waypoints: true },
  { id: 'route-planning', label: 'Route Planning', base: 'usgs-topo', hillshade: false, waypoints: true },
  { id: 'land-access', label: 'Land & Access', base: 'kytopo', hillshade: false, waypoints: true },
  { id: 'all-layers', label: 'All Layers', base: 'kentucky-aerial', hillshade: true, waypoints: true }
] as const;

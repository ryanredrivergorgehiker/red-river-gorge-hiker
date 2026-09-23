export const mapPresets = {
  simple: {
    label: 'Simple',
    base: 'kytopo',
    overlays: ['routes', 'waypoints']
  },
  terrain: {
    label: 'Terrain',
    base: 'kytopo',
    overlays: ['ky-hillshade', 'routes', 'waypoints']
  },
  routePlanning: {
    label: 'Route Planning',
    base: 'kytopo',
    overlays: ['routes', 'waypoints']
  },
  landAccess: {
    label: 'Land & Access',
    base: 'usgs-topo',
    overlays: ['routes', 'waypoints']
  },
  allLayers: {
    label: 'All Layers',
    base: 'kytopo',
    overlays: ['ky-hillshade', 'routes', 'waypoints']
  }
} as const;

export type MapPresetId = keyof typeof mapPresets;

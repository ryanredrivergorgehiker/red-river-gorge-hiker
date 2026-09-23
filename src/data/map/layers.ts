export type RasterLayerId = 'kytopo' | 'kentucky-hillshade' | 'kentucky-aerial' | 'usgs-topo';

export interface RasterLayerSource {
  id: RasterLayerId;
  label: string;
  kind: 'base' | 'overlay';
  enabled: true;
  tileUrl: string;
  attribution: string;
  providerHost: string;
  maxZoom: number;
  opacity?: number;
  privacyNote: string;
}

export const rasterLayers: RasterLayerSource[] = [
  {
    id: 'kytopo',
    label: 'Kentucky Topo / KyTopo',
    kind: 'base',
    enabled: true,
    tileUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_KyTopo_Map_Series_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    attribution: 'KyFromAbove Partners, Kentucky Division of Geographic Information',
    providerHost: 'kygisserver.ky.gov',
    maxZoom: 19,
    privacyNote: 'Direct browser tile requests to Kentucky DGI; separate from RRGH Analytics.'
  },
  {
    id: 'kentucky-hillshade',
    label: 'Kentucky LiDAR multidirectional hillshade',
    kind: 'overlay',
    enabled: true,
    tileUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_MultiDirectional_Hillshade_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    attribution: 'KyFromAbove / Commonwealth of Kentucky',
    providerHost: 'kygisserver.ky.gov',
    maxZoom: 19,
    opacity: 0.62,
    privacyNote: 'Direct browser tile requests to Kentucky DGI; separate from RRGH Analytics.'
  },
  {
    id: 'kentucky-aerial',
    label: 'Kentucky Phase 3 aerial imagery',
    kind: 'base',
    enabled: true,
    tileUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase3_3IN_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    attribution: 'KyFromAbove / Commonwealth of Kentucky',
    providerHost: 'kygisserver.ky.gov',
    maxZoom: 21,
    privacyNote: 'Direct browser tile requests to Kentucky DGI; separate from RRGH Analytics.'
  },
  {
    id: 'usgs-topo',
    label: 'USGS Topo',
    kind: 'base',
    enabled: true,
    tileUrl: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',
    attribution: 'USGS The National Map',
    providerHost: 'basemap.nationalmap.gov',
    maxZoom: 16,
    privacyNote: 'Direct browser tile requests to USGS; separate from RRGH Analytics.'
  }
];

export const disabledReferenceLayers = [
  {
    id: 'usfs-local-reference',
    label: 'Forest Service trails / MVUM / Wilderness / NFS land',
    reason: 'Registered source family, but deterministic RRGH-area snapshots are not yet committed in this initial staging candidate.'
  },
  {
    id: 'parcel-private-property',
    label: 'Parcel / private-property boundaries',
    reason: 'Disabled: no qualifying authorized source has been approved under LEG-DEC-0028.'
  }
] as const;

export type MapSourceKind = 'base' | 'overlay' | 'reference' | 'elevation';

export interface MapSource {
  id: string;
  label: string;
  kind: MapSourceKind;
  enabled: boolean;
  browserLoaded: boolean;
  url?: string;
  serviceUrl: string;
  attribution: string;
  termsUrl: string;
  privacyNote: string;
  minZoom?: number;
  maxZoom?: number;
  opacity?: number;
}

export const mapSources: readonly MapSource[] = [
  {
    id: 'kytopo',
    label: 'Kentucky Topo / KyTopo',
    kind: 'base',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_KyTopo_Map_Series_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    serviceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_KyTopo_Map_Series_WGS84WM/MapServer',
    attribution: 'KyFromAbove Partners / Kentucky Division of Geographic Information',
    termsUrl: 'https://kyfromabove.ky.gov/',
    privacyNote: 'Browser tile requests go directly to kygisserver.ky.gov and are separate from RRGH Analytics.',
    minZoom: 5,
    maxZoom: 19
  },
  {
    id: 'kyaerial-phase3',
    label: 'Kentucky Phase 3 Aerial',
    kind: 'base',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase3_3IN_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    serviceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase3_3IN_WGS84WM/MapServer',
    attribution: 'KyFromAbove / Commonwealth of Kentucky',
    termsUrl: 'https://kyfromabove.ky.gov/',
    privacyNote: 'Browser tile requests go directly to kygisserver.ky.gov and are separate from RRGH Analytics.',
    minZoom: 5,
    maxZoom: 20
  },
  {
    id: 'ky-hillshade',
    label: 'Kentucky LiDAR / Multidirectional Hillshade',
    kind: 'overlay',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_MultiDirectional_Hillshade_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    serviceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_MultiDirectional_Hillshade_WGS84WM/MapServer',
    attribution: 'KyFromAbove / Commonwealth of Kentucky',
    termsUrl: 'https://kyfromabove.ky.gov/',
    privacyNote: 'Browser tile requests go directly to kygisserver.ky.gov and are separate from RRGH Analytics.',
    minZoom: 5,
    maxZoom: 19,
    opacity: 0.52
  },
  {
    id: 'usgs-topo',
    label: 'USGS Topo',
    kind: 'base',
    enabled: true,
    browserLoaded: true,
    url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',
    serviceUrl: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer',
    attribution: 'USGS The National Map',
    termsUrl: 'https://www.usgs.gov/faqs/what-are-terms-uselicensing-map-services-and-data-national-map',
    privacyNote: 'Browser tile requests go directly to basemap.nationalmap.gov and are separate from RRGH Analytics.',
    minZoom: 5,
    maxZoom: 16
  },
  {
    id: 'usfs-reference-snapshots',
    label: 'USFS Trails / Roads / MVUM / Wilderness / NFS Land Units',
    kind: 'reference',
    enabled: false,
    browserLoaded: false,
    serviceUrl: 'https://data.fs.usda.gov/geodata/edw/datasets.php',
    attribution: 'USDA Forest Service',
    termsUrl: 'https://data.fs.usda.gov/geodata/edw/datasets.php',
    privacyNote: 'Registered for future clipped local snapshots; no live Forest Service browser layer is enabled in this initial staging implementation.'
  },
  {
    id: 'parcel-private-property',
    label: 'Parcel / Private Property',
    kind: 'reference',
    enabled: false,
    browserLoaded: false,
    serviceUrl: '',
    attribution: '',
    termsUrl: '',
    privacyNote: 'Disabled. No authorized source is approved under LEG-DEC-0028.'
  },
  {
    id: 'usgs-3dep-bare-earth-dem',
    label: 'USGS 3DEP Bare Earth DEM',
    kind: 'elevation',
    enabled: true,
    browserLoaded: false,
    serviceUrl: 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer',
    attribution: 'USGS National Map 3D Elevation Program (3DEP)',
    termsUrl: 'https://www.usgs.gov/faqs/what-are-terms-uselicensing-map-services-and-data-national-map',
    privacyNote: 'Build-time only. Visitor browsers do not call the elevation service.'
  }
] as const;

export const enabledBrowserMapSources = mapSources.filter((source) => source.enabled && source.browserLoaded);
export const elevationSource = mapSources.find((source) => source.id === 'usgs-3dep-bare-earth-dem')!;

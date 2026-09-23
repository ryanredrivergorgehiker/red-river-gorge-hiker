export type MapLayerKind = 'base' | 'overlay' | 'reference' | 'elevation';

export interface MapLayerRecord {
  id: string;
  label: string;
  kind: MapLayerKind;
  enabled: boolean;
  browserLoaded: boolean;
  url: string;
  sourceUrl: string;
  attribution: string;
  maxZoom?: number;
  minZoom?: number;
  defaultOpacity?: number;
  useBasis: string;
  privacy: string;
  implementation: string;
  lastVerified: string;
}

export const mapLayers: MapLayerRecord[] = [
  {
    id: 'kytopo',
    label: 'Kentucky Topo / KyTopo',
    kind: 'base',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_KyTopo_Map_Series_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    sourceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_KyTopo_Map_Series_WGS84WM/MapServer',
    attribution: 'KyFromAbove Partners / Kentucky Division of Geographic Information',
    maxZoom: 19,
    useBasis: 'Official Kentucky cached Web Mercator service intended for web mapping; KyFromAbove program data acquired by the Commonwealth is distributed as public-domain data.',
    privacy: 'Direct browser tile requests go to kygisserver.ky.gov and are separate from RRGH Analytics.',
    implementation: 'Enabled staging base layer.',
    lastVerified: '2026-09-23'
  },
  {
    id: 'ky-hillshade',
    label: 'Kentucky LiDAR multidirectional hillshade',
    kind: 'overlay',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_MultiDirectional_Hillshade_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    sourceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_MultiDirectional_Hillshade_WGS84WM/MapServer',
    attribution: 'KyFromAbove / Kentucky Division of Geographic Information',
    maxZoom: 19,
    defaultOpacity: 0.62,
    useBasis: 'Official Kentucky cached multidirectional hillshade based on KYAPED 5-foot DEM.',
    privacy: 'Direct browser tile requests go to kygisserver.ky.gov and are separate from RRGH Analytics.',
    implementation: 'Enabled staging terrain overlay.',
    lastVerified: '2026-09-23'
  },
  {
    id: 'ky-aerial',
    label: 'Kentucky Phase 3 3-inch imagery',
    kind: 'base',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase3_3IN_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    sourceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase3_3IN_WGS84WM/MapServer',
    attribution: 'KyFromAbove / Kentucky Division of Geographic Information',
    maxZoom: 21,
    useBasis: 'Official Kentucky Web Mercator imagery service.',
    privacy: 'Direct browser tile requests go to kygisserver.ky.gov and are separate from RRGH Analytics.',
    implementation: 'Enabled staging aerial base layer.',
    lastVerified: '2026-09-23'
  },
  {
    id: 'usgs-topo',
    label: 'USGS Topo',
    kind: 'base',
    enabled: true,
    browserLoaded: true,
    url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',
    sourceUrl: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer',
    attribution: 'USGS The National Map',
    maxZoom: 16,
    useBasis: 'USGS National Map public-domain map/data service with requested acknowledgment and embedded source credits.',
    privacy: 'Direct browser tile requests go to basemap.nationalmap.gov and are separate from RRGH Analytics.',
    implementation: 'Enabled staging secondary topo base layer.',
    lastVerified: '2026-09-23'
  },
  {
    id: 'usgs-3dep-epqs',
    label: 'USGS 3DEP Elevation Point Query Service',
    kind: 'elevation',
    enabled: true,
    browserLoaded: false,
    url: 'https://epqs.nationalmap.gov/v1/json',
    sourceUrl: 'https://apps.nationalmap.gov/epqs/',
    attribution: 'USGS 3D Elevation Program (3DEP)',
    useBasis: 'USGS National Map public-domain elevation service. Used only during controlled static profile generation.',
    privacy: 'No visitor request. Generation tooling submits approved public route coordinates only.',
    implementation: 'Approved elevation-profile generation source.',
    lastVerified: '2026-09-23'
  },
  {
    id: 'usfs-trails',
    label: 'US Forest Service NFS Trails',
    kind: 'reference',
    enabled: false,
    browserLoaded: false,
    url: 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer',
    sourceUrl: 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer',
    attribution: 'USDA Forest Service Enterprise Data Warehouse',
    useBasis: 'Official public trail dataset; forest-level readiness varies.',
    privacy: 'Disabled. No visitor requests.',
    implementation: 'Requires a clipped/simplified local snapshot before activation.',
    lastVerified: '2026-09-23'
  },
  {
    id: 'usfs-wilderness',
    label: 'US Forest Service Wilderness boundaries',
    kind: 'reference',
    enabled: false,
    browserLoaded: false,
    url: 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_Wilderness_01/MapServer',
    sourceUrl: 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_Wilderness_01/MapServer',
    attribution: 'USDA Forest Service Enterprise Map Service Program',
    useBasis: 'Official informational wilderness boundaries; not a survey/title/access determination.',
    privacy: 'Disabled. No visitor requests.',
    implementation: 'Requires a clipped/simplified local snapshot before activation.',
    lastVerified: '2026-09-23'
  },
  {
    id: 'usfs-basic-ownership',
    label: 'US Forest Service basic ownership',
    kind: 'reference',
    enabled: false,
    browserLoaded: false,
    url: 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_BasicOwnership_01/MapServer',
    sourceUrl: 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_BasicOwnership_01/MapServer',
    attribution: 'USDA Forest Service Enterprise Map Service Program',
    useBasis: 'Official informational surface-ownership dataset; expressly not a legal title/boundary/access determination.',
    privacy: 'Disabled. No visitor requests.',
    implementation: 'Requires a clipped/simplified local snapshot before activation.',
    lastVerified: '2026-09-23'
  },
  {
    id: 'parcel-private-property',
    label: 'Parcel / private-property boundaries',
    kind: 'reference',
    enabled: false,
    browserLoaded: false,
    url: '',
    sourceUrl: '',
    attribution: '',
    useBasis: 'No authorized RRGH source selected.',
    privacy: 'Disabled. No visitor requests.',
    implementation: 'BLOCKED. Material source/legal/privacy change required before activation.',
    lastVerified: '2026-09-23'
  }
];

export const enabledBrowserMapLayers = mapLayers.filter((layer) => layer.enabled && layer.browserLoaded);

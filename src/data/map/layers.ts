export type MapSourceKind = 'tile' | 'vector' | 'reference' | 'elevation';

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
  maxNativeZoom?: number;
  opacity?: number;
}

const RRG_QUERY_BOUNDS = '-84.02,37.52,-83.18,38.15';

const arcgisGeoJsonQuery = (serviceUrl: string, outFields: string) => {
  const params = new URLSearchParams({
    where: '1=1',
    geometry: RRG_QUERY_BOUNDS,
    geometryType: 'esriGeometryEnvelope',
    inSR: '4326',
    spatialRel: 'esriSpatialRelIntersects',
    outFields,
    returnGeometry: 'true',
    outSR: '4326',
    f: 'geojson'
  });
  return `${serviceUrl}/query?${params.toString()}`;
};

const trailService = 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublishWithDataStatus_01/MapServer/0';
const roadService = 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_RoadBasic_01/MapServer/0';
const countyService = 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_CountyLines_WGS84WM/MapServer/0';

export const mapSources: readonly MapSource[] = [
  {
    id: 'kytopo',
    label: 'Kentucky Topo',
    kind: 'tile',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_KyTopo_Map_Series_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    serviceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_KyTopo_Map_Series_WGS84WM/MapServer',
    attribution: 'KyFromAbove Partners / Kentucky Division of Geographic Information',
    termsUrl: 'https://kyfromabove.ky.gov/',
    privacyNote: 'Map tiles are requested directly from the Kentucky Division of Geographic Information.',
    minZoom: 5,
    maxZoom: 20,
    maxNativeZoom: 19,
    opacity: 1
  },
  {
    id: 'kyaerial-phase3',
    label: 'Aerial imagery',
    kind: 'tile',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase3_3IN_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    serviceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase3_3IN_WGS84WM/MapServer',
    attribution: 'KyFromAbove / Commonwealth of Kentucky',
    termsUrl: 'https://kyfromabove.ky.gov/',
    privacyNote: 'Imagery tiles are requested directly from the Kentucky Division of Geographic Information.',
    minZoom: 5,
    maxZoom: 20,
    opacity: 0.7
  },
  {
    id: 'usgs-topo',
    label: 'USGS Topo',
    kind: 'tile',
    enabled: true,
    browserLoaded: true,
    url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',
    serviceUrl: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer',
    attribution: 'USGS The National Map',
    termsUrl: 'https://www.usgs.gov/faqs/what-are-terms-uselicensing-map-services-and-data-national-map',
    privacyNote: 'Topo tiles are requested directly from USGS The National Map.',
    minZoom: 5,
    maxZoom: 20,
    maxNativeZoom: 16,
    opacity: 0.7
  },
  {
    id: 'ky-hillshade',
    label: 'LiDAR hillshade',
    kind: 'tile',
    enabled: true,
    browserLoaded: true,
    url: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_MultiDirectional_Hillshade_WGS84WM/MapServer/tile/{z}/{y}/{x}',
    serviceUrl: 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_MultiDirectional_Hillshade_WGS84WM/MapServer',
    attribution: 'KyFromAbove / Commonwealth of Kentucky',
    termsUrl: 'https://kyfromabove.ky.gov/',
    privacyNote: 'Hillshade tiles are requested directly from the Kentucky Division of Geographic Information.',
    minZoom: 5,
    maxZoom: 20,
    maxNativeZoom: 19,
    opacity: 0.28
  },
  {
    id: 'usfs-trails',
    label: 'Forest Service trails',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    url: arcgisGeoJsonQuery(trailService, 'trail_name,trail_no,trail_class,attributesubset'),
    serviceUrl: trailService,
    attribution: 'USDA Forest Service',
    termsUrl: 'https://data.fs.usda.gov/geodata/edw/datasets.php',
    privacyNote: 'Trail geometry is requested directly from the USDA Forest Service Enterprise Data Warehouse.',
    opacity: 0.45
  },
  {
    id: 'usfs-roads',
    label: 'Forest Service roads',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    url: arcgisGeoJsonQuery(roadService, 'name,id,route_status,oper_maint_level'),
    serviceUrl: roadService,
    attribution: 'USDA Forest Service',
    termsUrl: 'https://data.fs.usda.gov/geodata/edw/datasets.php',
    privacyNote: 'Road geometry is requested directly from the USDA Forest Service Enterprise Data Warehouse.',
    opacity: 0.6
  },
  {
    id: 'ky-counties',
    label: 'County boundaries',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    url: arcgisGeoJsonQuery(countyService, 'NAME,ABBREVTN'),
    serviceUrl: countyService,
    attribution: 'Kentucky Division of Geographic Information',
    termsUrl: 'https://kygeoportal.ky.gov/',
    privacyNote: 'County boundary geometry is requested directly from the Kentucky Division of Geographic Information.',
    opacity: 0.6
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
    privacyNote: 'Disabled. No authorized parcel/private-property source is currently approved for this map.'
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

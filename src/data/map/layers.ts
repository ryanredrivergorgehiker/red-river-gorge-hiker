export type MapSourceKind = 'tile' | 'vector' | 'reference' | 'elevation' | 'derived';

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
const kentuckyRoadCenterlineService = 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_911_Road_Centerlines_WGS84WM/MapServer/0';
const recreationSiteService = 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_RecInfraRecreationSites_02/MapServer/0';
const wildernessService = 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_Wilderness_01/MapServer/0';
const specialManagementService = 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_SpecialInterestManagementArea_01/MapServer/0';
const nfsLandUnitService = 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_NFSLandUnit_01/MapServer/0';
const overpassService = 'https://www.openstreetmap.org/copyright';

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
    label: 'Terrain relief (LiDAR)',
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
    id: 'ky-road-centerlines',
    label: 'Kentucky road centerlines (route planning)',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    url: arcgisGeoJsonQuery(kentuckyRoadCenterlineService, 'LSt_Name,St_Name,RoadClass,SpeedLimit,OneWay'),
    serviceUrl: kentuckyRoadCenterlineService,
    attribution: 'Kentucky 911 Services Board & Kentucky PSAPs',
    termsUrl: 'https://kygeoportal.ky.gov/',
    privacyNote: 'A fixed Red River Gorge-area road-centerline query is requested from Kentucky GIS for route-planning geometry. It is not based on the visitor’s location and does not establish pedestrian access, safety, or current road status.',
    opacity: 0
  },
  {
    id: 'usfs-recreation-sites',
    label: 'Trailheads & facilities',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    url: arcgisGeoJsonQuery(recreationSiteService, 'site_name,public_site_name,site_type,seasonal_operational_status,development_status,recarea_name,usda_portal_url,latitude,longitude'),
    serviceUrl: recreationSiteService,
    attribution: 'USDA Forest Service',
    termsUrl: 'https://data.fs.usda.gov/geodata/edw/datasets.php',
    privacyNote: 'Recreation-site locations and public site information are requested directly from the USDA Forest Service Enterprise Data Warehouse.',
    opacity: 1
  },
  {
    id: 'usfs-wilderness',
    label: 'National Forest Wilderness',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    url: arcgisGeoJsonQuery(wildernessService, 'wildernessname,boundarystatus,gis_acres'),
    serviceUrl: wildernessService,
    attribution: 'USDA Forest Service',
    termsUrl: 'https://data.fs.usda.gov/geodata/edw/datasets.php',
    privacyNote: 'Wilderness boundaries are requested directly from the USDA Forest Service Enterprise Data Warehouse.',
    opacity: 0.72
  },
  {
    id: 'usfs-special-management',
    label: 'Special management areas',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    url: arcgisGeoJsonQuery(specialManagementService, 'casename,areaname,areatype,boundarystatus'),
    serviceUrl: specialManagementService,
    attribution: 'USDA Forest Service',
    termsUrl: 'https://data.fs.usda.gov/geodata/edw/datasets.php',
    privacyNote: 'Special-interest management-area boundaries are requested directly from the USDA Forest Service Enterprise Data Warehouse.',
    opacity: 0.66
  },
  {
    id: 'usfs-land-units',
    label: 'National Forest land units',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    url: arcgisGeoJsonQuery(nfsLandUnitService, 'nfslandunitname,nfslandunittype'),
    serviceUrl: nfsLandUnitService,
    attribution: 'USDA Forest Service',
    termsUrl: 'https://data.fs.usda.gov/geodata/edw/datasets.php',
    privacyNote: 'National Forest System land-unit boundaries are requested directly from the USDA Forest Service Enterprise Data Warehouse.',
    opacity: 0.45
  },
  {
    id: 'osm-informal-trails',
    label: 'Community / Informal trails',
    kind: 'vector',
    enabled: true,
    browserLoaded: true,
    serviceUrl: overpassService,
    attribution: '© OpenStreetMap contributors',
    termsUrl: 'https://www.openstreetmap.org/copyright',
    privacyNote: 'Community / Informal trails normally load from an RRGH-hosted OpenStreetMap-derived cache. Public Overpass API instances are used only as a browser fallback if the cache is unavailable. The cache includes paths explicitly tagged informal plus community-mapped path/footway candidates that do not substantially match RRGH\'s authoritative USDA Forest Service trail geometry. Appearance on this layer is not proof of legal access, maintenance, or official status.',
    opacity: 1
  },
  {
    id: 'sunrise-sunset-potential',
    label: 'Sunrise / Sunset potential',
    kind: 'derived',
    enabled: true,
    browserLoaded: true,
    serviceUrl: 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer',
    attribution: 'Red River Gorge Hiker high-ground model derived from USGS 3DEP elevation and © OpenStreetMap contributors water features',
    termsUrl: 'https://www.openstreetmap.org/copyright',
    privacyNote: 'This RRGH-hosted derived overlay is generated in advance from fixed Red River Gorge USGS elevation and OpenStreetMap water data. Mapped water and low valley terrain are suppressed. Viewing it sends no coordinates or map requests to USGS. It indicates seasonal high-ground potential for sunrise and sunset photography, not guaranteed visibility.',
    opacity: 0.68
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
    browserLoaded: true,
    serviceUrl: 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer',
    attribution: 'USGS National Map 3D Elevation Program (3DEP)',
    termsUrl: 'https://www.usgs.gov/faqs/what-are-terms-uselicensing-map-services-and-data-national-map',
    privacyNote: 'Approved route elevation remains generated at build time. When a visitor uses Measure distance or Build trail route, sampled planning coordinates are sent directly from the browser to USGS 3DEP only to calculate the requested elevation feedback.'
  }
] as const;

export const enabledBrowserMapSources = mapSources.filter((source) => source.enabled && source.browserLoaded);
export const elevationSource = mapSources.find((source) => source.id === 'usgs-3dep-bare-earth-dem')!;

export const SAR_REPORTING_SOURCE = 'Red River Gorge Hiker - Bookkeeping Ledger / SAR Public Reporting' as const;

export const SAR_PUBLIC_CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vRuKVBO_LFcCBu-gZL9vHVsLwP2w7KNi1bUbgeDTUvCbtdsP5Osc9Ky2Wuz4FgyOfeGy1SY0tbSrif0/pub?gid=1698631448&single=true&output=csv' as const;

export const SAR_PUBLIC_FIELDS = [
  'reportingYear',
  'rrghAnnualBaseCommitment',
  'rrghProfitAllocationGenerated',
  'rrghTotalCommitment',
  'rrghBaseCommitmentTransferred',
  'rrghProfitAllocationTransferred',
  'rrghTotalTransferred',
  'outstandingBaseCommitment',
  'outstandingProfitAllocation',
  'outstandingRrghCommitment',
  'commitmentFulfillmentPercentage',
  'historicalPersonalSupport',
  'lifetimePersonalSupport',
  'lifetimeRrghCommitted',
  'lifetimeRrghTransferred',
  'combinedLifetimeSupport',
  'lastUpdated'
] as const;

// Last-known-good public snapshot used only while the published CSV is unavailable.
// The live website display is refreshed from SAR_PUBLIC_CSV_URL at runtime. These values
// are not a second accounting source and must be refreshed only from the ledger-approved
// SAR Website Public Data handoff when a production release updates the fallback snapshot.
export const sar = {
  reportingYear: 2026,
  rrghAnnualBaseCommitment: 500,
  rrghProfitAllocationGenerated: 0,
  rrghTotalCommitment: 500,
  rrghBaseCommitmentTransferred: 0,
  rrghProfitAllocationTransferred: 0,
  rrghTotalTransferred: 0,
  outstandingBaseCommitment: 500,
  outstandingProfitAllocation: 0,
  outstandingRrghCommitment: 500,
  commitmentFulfillmentPercentage: 0,
  historicalPersonalSupport: 500,
  lifetimePersonalSupport: 500,
  lifetimeRrghCommitted: 500,
  lifetimeRrghTransferred: 0,
  combinedLifetimeSupport: 500,
  lastUpdated: '2026-09-19T14:39:00-04:00',
  source: SAR_REPORTING_SOURCE
} as const;

export const sarLinks = {
  wcsart: 'https://wcsart.com/',
  donate: 'https://wcsart.com/donate/',
  forestServiceAlerts: 'https://www.fs.usda.gov/alerts/dbnf/alerts-notices/?aid=77606',
  forestServiceMaps: 'https://www.fs.usda.gov/r08/danielboone/maps-guides',
  cliftyWilderness: 'https://www.fs.usda.gov/r08/danielboone/recreation/clifty-wilderness',
  gladieVisitorCenter: 'https://www.fs.usda.gov/r08/danielboone/recreation/gladie-visitor-center',
  naturalBridge: 'https://parks.ky.gov/explore/natural-bridge-state-resort-park-7796',
  nwsSlade: 'https://forecast.weather.gov/MapClick.php?lat=37.783&lon=-83.683',
  goKy: 'https://goky.ky.gov/',
  npsTenEssentials: 'https://www.nps.gov/articles/10essentials.htm',
  npsHikeSmart: 'https://www.nps.gov/articles/hiking-safety.htm',
  powellSar: 'https://www.pocosar.org/',
  leeCountyEmergencyManagement: 'https://leecounty.ky.gov/elected/Pages/default.aspx',
  menifeeCountyGovernment: 'https://menifeecounty.ky.gov/Pages/contact.aspx'
} as const;

// These are content-review dates, not financial-calculation dates. Changeable rules stay linked
// to their controlling agencies so visitors can confirm current conditions before a trip.
export const sarContentReview = {
  campingRules: '2026-08-09',
  safetyResources: '2026-08-09',
  externalResources: '2026-08-09'
} as const;

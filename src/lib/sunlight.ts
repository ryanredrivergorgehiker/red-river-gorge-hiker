export const RRG_TIME_ZONE = 'America/New_York';
export const STANDARD_SUN_ALTITUDE_DEG = -0.833;

const RAD = Math.PI / 180;
const DAY_MS = 86400000;
const J1970 = 2440588;
const J2000 = 2451545;
const EARTH_RADIUS_M = 6371008.8;
const EFFECTIVE_EARTH_RADIUS_M = EARTH_RADIUS_M * (7 / 6);

export interface RrgLocalDate {
  year: number;
  month: number;
  day: number;
}

export interface SunPosition {
  altitudeDeg: number;
  azimuthDeg: number;
}

export interface AstronomicalSunDay {
  date: RrgLocalDate;
  start: Date;
  end: Date;
  sunrise: Date | null;
  sunset: Date | null;
}

export interface TerrainSamplePoint {
  lat: number;
  lng: number;
  azimuthDeg: number;
  distanceM: number;
}

export interface TerrainHorizonProfile {
  azimuthStepDeg: number;
  anglesDeg: number[];
}

export interface TerrainDirectTimes {
  firstDirectSun: Date | null;
  lastDirectSun: Date | null;
}

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: RRG_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit'
});

const wallClockFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: RRG_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23'
});

const timeFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: RRG_TIME_ZONE,
  hour: 'numeric',
  minute: '2-digit'
});

const shortDateFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: RRG_TIME_ZONE,
  weekday: 'short',
  month: 'short',
  day: 'numeric'
});

const numericParts = (formatter: Intl.DateTimeFormat, date: Date) => {
  const values: Record<string, number> = {};
  for (const part of formatter.formatToParts(date)) {
    if (part.type !== 'literal') values[part.type] = Number(part.value);
  }
  return values;
};

export const redRiverDateParts = (date = new Date()): RrgLocalDate => {
  const values = numericParts(dateFormatter, date);
  return { year: values.year!, month: values.month!, day: values.day! };
};

export const addLocalDays = (date: RrgLocalDate, offset: number): RrgLocalDate => {
  const value = new Date(Date.UTC(date.year, date.month - 1, date.day + offset, 12));
  return { year: value.getUTCFullYear(), month: value.getUTCMonth() + 1, day: value.getUTCDate() };
};

const zonedDateTimeToUtc = (date: RrgLocalDate, hour = 0, minute = 0, second = 0) => {
  const targetWall = Date.UTC(date.year, date.month - 1, date.day, hour, minute, second);
  let guess = targetWall;
  for (let iteration = 0; iteration < 4; iteration += 1) {
    const wall = numericParts(wallClockFormatter, new Date(guess));
    const representedWall = Date.UTC(
      wall.year!, wall.month! - 1, wall.day!,
      wall.hour!, wall.minute!, wall.second!
    );
    const correction = targetWall - representedWall;
    guess += correction;
    if (Math.abs(correction) < 1000) break;
  }
  return new Date(guess);
};

export const formatRrgTime = (date: Date | null) => date ? timeFormatter.format(date) : '—';
export const formatRrgDate = (date: Date) => shortDateFormatter.format(date);

const toJulian = (date: Date) => date.getTime() / DAY_MS - 0.5 + J1970;
const toDays = (date: Date) => toJulian(date) - J2000;
const solarMeanAnomaly = (days: number) => RAD * (357.5291 + 0.98560028 * days);
const eclipticLongitude = (meanAnomaly: number) => {
  const equation = RAD * (
    1.9148 * Math.sin(meanAnomaly)
    + 0.02 * Math.sin(2 * meanAnomaly)
    + 0.0003 * Math.sin(3 * meanAnomaly)
  );
  return meanAnomaly + equation + RAD * 102.9372 + Math.PI;
};
const obliquity = RAD * 23.4397;
const declination = (longitude: number) =>
  Math.asin(Math.sin(longitude) * Math.sin(obliquity));
const rightAscension = (longitude: number) =>
  Math.atan2(Math.sin(longitude) * Math.cos(obliquity), Math.cos(longitude));
const siderealTime = (days: number, longitudeWestRad: number) =>
  RAD * (280.16 + 360.9856235 * days) - longitudeWestRad;

export const getSunPosition = (date: Date, lat: number, lng: number): SunPosition => {
  const longitudeWest = RAD * -lng;
  const latitude = RAD * lat;
  const days = toDays(date);
  const meanAnomaly = solarMeanAnomaly(days);
  const longitude = eclipticLongitude(meanAnomaly);
  const sunDeclination = declination(longitude);
  const hourAngle = siderealTime(days, longitudeWest) - rightAscension(longitude);

  const altitude = Math.asin(
    Math.sin(latitude) * Math.sin(sunDeclination)
    + Math.cos(latitude) * Math.cos(sunDeclination) * Math.cos(hourAngle)
  );
  const sunAzimuth = Math.atan2(
    Math.sin(hourAngle),
    Math.cos(hourAngle) * Math.sin(latitude) - Math.tan(sunDeclination) * Math.cos(latitude)
  );

  return {
    altitudeDeg: altitude / RAD,
    azimuthDeg: ((sunAzimuth / RAD + 180) % 360 + 360) % 360
  };
};

const refineAltitudeCrossing = (
  lowerMs: number,
  upperMs: number,
  lat: number,
  lng: number,
  rising: boolean
) => {
  let low = lowerMs;
  let high = upperMs;
  for (let iteration = 0; iteration < 18; iteration += 1) {
    const mid = (low + high) / 2;
    const above = getSunPosition(new Date(mid), lat, lng).altitudeDeg >= STANDARD_SUN_ALTITUDE_DEG;
    if (rising ? above : !above) high = mid;
    else low = mid;
  }
  return new Date((low + high) / 2);
};

export const getAstronomicalSunDay = (
  lat: number,
  lng: number,
  date: RrgLocalDate
): AstronomicalSunDay => {
  const start = zonedDateTimeToUtc(date, 0, 0, 0);
  const end = zonedDateTimeToUtc(addLocalDays(date, 1), 0, 0, 0);
  const stepMs = 4 * 60 * 1000;
  let sunrise: Date | null = null;
  let sunset: Date | null = null;
  let previousMs = start.getTime();
  let previousAbove = getSunPosition(start, lat, lng).altitudeDeg >= STANDARD_SUN_ALTITUDE_DEG;

  for (let currentMs = previousMs + stepMs; currentMs <= end.getTime(); currentMs += stepMs) {
    const currentAbove = getSunPosition(new Date(currentMs), lat, lng).altitudeDeg >= STANDARD_SUN_ALTITUDE_DEG;
    if (!previousAbove && currentAbove && !sunrise) {
      sunrise = refineAltitudeCrossing(previousMs, currentMs, lat, lng, true);
    }
    if (previousAbove && !currentAbove) {
      sunset = refineAltitudeCrossing(previousMs, currentMs, lat, lng, false);
    }
    previousMs = currentMs;
    previousAbove = currentAbove;
  }

  return { date, start, end, sunrise, sunset };
};

const destinationPoint = (lat: number, lng: number, bearingDeg: number, distanceM: number) => {
  const angular = distanceM / EARTH_RADIUS_M;
  const bearing = bearingDeg * RAD;
  const lat1 = lat * RAD;
  const lng1 = lng * RAD;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular)
    + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing)
  );
  const lng2 = lng1 + Math.atan2(
    Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
    Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2)
  );
  return {
    lat: lat2 / RAD,
    lng: ((lng2 / RAD + 540) % 360) - 180
  };
};

export const buildTerrainSamplePoints = (
  lat: number,
  lng: number,
  azimuthStepDeg = 5,
  distancesM = [20, 40, 80, 160, 320, 640, 1280, 2560, 5000]
): TerrainSamplePoint[] => {
  const result: TerrainSamplePoint[] = [];
  for (let azimuthDeg = 0; azimuthDeg < 360; azimuthDeg += azimuthStepDeg) {
    for (const distanceM of distancesM) {
      const point = destinationPoint(lat, lng, azimuthDeg, distanceM);
      result.push({ ...point, azimuthDeg, distanceM });
    }
  }
  return result;
};

export const buildTerrainHorizonProfile = (
  samples: TerrainSamplePoint[],
  elevationsMeters: Array<number | null>,
  azimuthStepDeg = 5,
  observerHeightMeters = 1.7
): TerrainHorizonProfile => {
  if (!Number.isFinite(elevationsMeters[0])) throw new Error('Terrain origin elevation is unavailable.');
  const originElevation = Number(elevationsMeters[0]);
  const count = Math.round(360 / azimuthStepDeg);
  const anglesDeg = Array.from({ length: count }, () => 0);

  for (let index = 0; index < samples.length; index += 1) {
    const elevation = elevationsMeters[index + 1];
    if (!Number.isFinite(elevation)) continue;
    const sample = samples[index]!;
    const curvatureDrop = sample.distanceM * sample.distanceM / (2 * EFFECTIVE_EARTH_RADIUS_M);
    const vertical = Number(elevation) - (originElevation + observerHeightMeters) - curvatureDrop;
    const angleDeg = Math.atan2(vertical, sample.distanceM) / RAD;
    const bucket = Math.round(sample.azimuthDeg / azimuthStepDeg) % count;
    anglesDeg[bucket] = Math.max(anglesDeg[bucket]!, angleDeg, 0);
  }

  return { azimuthStepDeg, anglesDeg };
};

export const terrainHorizonAtAzimuth = (profile: TerrainHorizonProfile, azimuthDeg: number) => {
  const azimuth = ((azimuthDeg % 360) + 360) % 360;
  const count = profile.anglesDeg.length;
  const position = azimuth / profile.azimuthStepDeg;
  const lowerIndex = Math.floor(position) % count;
  const upperIndex = (lowerIndex + 1) % count;
  const fraction = position - Math.floor(position);
  const lower = profile.anglesDeg[lowerIndex] ?? 0;
  const upper = profile.anglesDeg[upperIndex] ?? lower;
  return lower + (upper - lower) * fraction;
};

const terrainClear = (
  date: Date,
  lat: number,
  lng: number,
  profile: TerrainHorizonProfile
) => {
  const position = getSunPosition(date, lat, lng);
  const horizon = terrainHorizonAtAzimuth(profile, position.azimuthDeg);
  return position.altitudeDeg - STANDARD_SUN_ALTITUDE_DEG >= horizon;
};

const refineTerrainBoundary = (
  clearMs: number,
  blockedMs: number,
  lat: number,
  lng: number,
  profile: TerrainHorizonProfile
) => {
  let clear = clearMs;
  let blocked = blockedMs;
  for (let iteration = 0; iteration < 16; iteration += 1) {
    const mid = (clear + blocked) / 2;
    if (terrainClear(new Date(mid), lat, lng, profile)) clear = mid;
    else blocked = mid;
  }
  return new Date((clear + blocked) / 2);
};

export const getTerrainDirectTimes = (
  lat: number,
  lng: number,
  day: AstronomicalSunDay,
  profile: TerrainHorizonProfile
): TerrainDirectTimes => {
  if (!day.sunrise || !day.sunset) return { firstDirectSun: null, lastDirectSun: null };
  const startMs = day.sunrise.getTime();
  const endMs = day.sunset.getTime();
  const stepMs = 2 * 60 * 1000;

  let firstDirectSun: Date | null = null;
  if (terrainClear(day.sunrise, lat, lng, profile)) {
    firstDirectSun = day.sunrise;
  } else {
    let previousMs = startMs;
    for (let currentMs = Math.min(endMs, startMs + stepMs); currentMs <= endMs; currentMs += stepMs) {
      if (terrainClear(new Date(currentMs), lat, lng, profile)) {
        firstDirectSun = refineTerrainBoundary(currentMs, previousMs, lat, lng, profile);
        break;
      }
      previousMs = currentMs;
    }
  }

  let lastDirectSun: Date | null = null;
  if (terrainClear(day.sunset, lat, lng, profile)) {
    lastDirectSun = day.sunset;
  } else {
    let blockedMs = endMs;
    for (let currentMs = Math.max(startMs, endMs - stepMs); currentMs >= startMs; currentMs -= stepMs) {
      if (terrainClear(new Date(currentMs), lat, lng, profile)) {
        lastDirectSun = refineTerrainBoundary(currentMs, blockedMs, lat, lng, profile);
        break;
      }
      blockedMs = currentMs;
    }
  }

  return { firstDirectSun, lastDirectSun };
};

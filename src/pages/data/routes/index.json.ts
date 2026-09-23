import { getCollection } from 'astro:content';

export const prerender = true;

export async function GET() {
  const routes = await getCollection('routes');
  const payload = routes.map((entry) => ({
    routeId: entry.data.routeId,
    slug: entry.id,
    title: entry.data.title,
    publicationClass: entry.data.publicationClass,
    tripType: entry.data.tripType,
    trailStatus: entry.data.trailStatus,
    shape: entry.data.shape,
    distanceMi: entry.data.distanceMi,
    physicalDifficulty: entry.data.physicalDifficulty,
    navigationDifficulty: entry.data.navigationDifficulty,
    lastInformationReview: entry.data.lastInformationReview,
    geometryUrl: entry.data.webGeometry.publicPath,
    gpxUrl: entry.data.approvedPublicationGpx.publicPath,
    waypointCount: entry.data.publicWaypoints.length
  }));
  return new Response(JSON.stringify(payload, null, 2) + '\n', {
    headers: { 'Content-Type': 'application/json; charset=utf-8' }
  });
}

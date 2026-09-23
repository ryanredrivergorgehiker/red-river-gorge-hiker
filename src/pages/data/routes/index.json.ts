import { getCollection } from 'astro:content';
export const prerender = true;
export async function GET() {
  const base = import.meta.env.BASE_URL;
  const routes = (await getCollection('routes'))
    .filter((route) => route.data.publicationStatus === 'Approved — Publication Ready')
    .map((route) => ({
      slug: route.id,
      routeId: route.data.routeId,
      title: route.data.title,
      publicationClass: route.data.publicationClass,
      tripType: route.data.tripType,
      trailStatus: route.data.trailStatus,
      shape: route.data.shape,
      distanceMi: route.data.distanceMi,
      geometryUrl: `${base}${route.data.geometry.path}`,
      gpxUrl: `${base}${route.data.gpx.path}`,
      waypoints: route.data.waypoints
    }));
  return new Response(JSON.stringify({ routes }, null, 2), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}

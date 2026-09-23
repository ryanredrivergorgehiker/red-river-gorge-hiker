import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const waypoint = z.object({
  waypointId: z.string().min(1),
  name: z.string().min(1),
  type: z.enum(['Trailhead/Parking','Landmark','Viewpoint','Junction/Turnaround','Water','Camp','Hazard','Photo/Story feature','Other']),
  lat: z.number().min(-90).max(90),
  lon: z.number().min(-180).max(180),
  description: z.string().optional()
});

const sourceDependency = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  url: z.string().url(),
  note: z.string().optional()
});

const artifact = z.object({
  path: z.string().min(1),
  version: z.string().min(1),
  sha256: z.string().regex(/^[a-f0-9]{64}$/)
});

const routes = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/data/routes' }),
  schema: z.object({
    routeId: z.string().regex(/^RTE-\d{4}$/),
    title: z.string().min(1),
    publicationClass: z.enum(['A','B','C']),
    publicationStatus: z.literal('Approved — Publication Ready'),
    tripType: z.enum(['day-hike','backpacking','multi-day']),
    trailStatus: z.enum(['official','mixed','off-trail']),
    shape: z.enum(['loop','out-and-back','point-to-point']),
    distanceMi: z.number().positive(),
    ascentFt: z.number().nonnegative().nullable(),
    descentFt: z.number().nonnegative().nullable(),
    minElevationFt: z.number().nullable(),
    maxElevationFt: z.number().nullable(),
    elevationStatus: z.string().min(1),
    estimatedDuration: z.string().nullable().optional(),
    physicalDifficulty: z.string().min(1),
    navigationDifficulty: z.string().min(1),
    lastPersonallyTraveled: z.coerce.date(),
    lastInformationReview: z.coerce.date(),
    overview: z.string().optional(),
    routeDescription: z.string().optional(),
    terrain: z.string().optional(),
    accessParking: z.string().min(1),
    hazards: z.array(z.string().min(1)),
    waterCamping: z.array(z.string().min(1)),
    sensitiveHandling: z.string().min(1),
    waypoints: z.array(waypoint),
    gpx: artifact.extend({
      trackPointCount: z.number().int().positive(),
      waypointCount: z.number().int().nonnegative()
    }),
    geometry: artifact,
    elevation: artifact.nullable(),
    sourceDependencies: z.array(sourceDependency),
    relatedContent: z.array(z.object({
      label: z.string(),
      href: z.string(),
      kind: z.enum(['story','photograph','resource'])
    })).default([]),
    seoDescription: z.string().min(1)
  })
});

export const collections = { routes };

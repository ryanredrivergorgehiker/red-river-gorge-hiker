import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const waypointSchema = z.object({
  waypointId: z.string().regex(/^WP-\d{4}$/),
  name: z.string().min(1),
  type: z.enum(['Trailhead/Parking', 'Landmark', 'Viewpoint', 'Junction/Turnaround', 'Water', 'Camp', 'Hazard', 'Photo/Story feature', 'Other']),
  lat: z.number().min(-90).max(90),
  lon: z.number().min(-180).max(180)
});

const artifactSchema = z.object({
  filename: z.string().min(1),
  url: z.string().startsWith('/'),
  version: z.string().min(1),
  sha256: z.string().regex(/^[a-f0-9]{64}$/)
});

const routes = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/data/routes' }),
  schema: z.object({
    routeId: z.string().regex(/^RTE-\d{4}$/),
    title: z.string().min(1),
    publicationClass: z.enum(['A', 'B', 'C']),
    publicationStatus: z.literal('Approved — Publication Ready'),
    tripType: z.enum(['day-hike', 'backpacking', 'multi-day']),
    trailStatus: z.enum(['official', 'mixed', 'off-trail']),
    shape: z.enum(['loop', 'out-and-back', 'point-to-point']),
    distanceMi: z.number().positive(),
    estimatedDuration: z.string().nullable(),
    physicalDifficulty: z.string().min(1),
    navigationDifficulty: z.string().min(1),
    lastPersonallyTraveled: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    lastInformationReview: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    accessParking: z.string().min(1),
    hazards: z.array(z.string().min(1)),
    waterCamping: z.array(z.string().min(1)),
    landAccessReview: z.string().min(1),
    sensitivePublicNote: z.string().min(1),
    waypoints: z.array(waypointSchema),
    landManagerResources: z.array(z.object({
      label: z.string().min(1),
      url: z.string().url(),
      note: z.string().optional()
    })),
    relatedContext: z.string().nullable(),
    sourceDependencies: z.array(z.string().min(1)),
    seoDescription: z.string().min(1),
    gpx: artifactSchema,
    geometry: artifactSchema,
    elevation: z.object({
      url: z.string().startsWith('/'),
      sourceId: z.literal('USGS-3DEP'),
      methodId: z.literal('rrgh-usgs-3dep-getSamples-v1')
    })
  })
});

export const collections = { routes };

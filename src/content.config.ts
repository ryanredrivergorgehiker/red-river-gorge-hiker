import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const waypointSchema = z.object({
  waypointId: z.string().regex(/^WP-\d{4}$/),
  name: z.string().min(1),
  type: z.string().min(1),
  lat: z.number().min(-90).max(90),
  lon: z.number().min(-180).max(180),
  description: z.string().min(1)
});

const publicArtifactSchema = z.object({
  filename: z.string().min(1),
  publicPath: z.string().startsWith('/'),
  version: z.string().min(1),
  sha256: z.string().regex(/^[a-f0-9]{64}$/)
});

const routes = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/data/routes' }),
  schema: z.object({
    routeId: z.string().regex(/^RTE-\d{4}$/),
    title: z.string().min(1),
    publicationClass: z.enum(['A', 'B', 'C']),
    publicationStatus: z.literal('Approved — Publication Ready'),
    tripType: z.enum(['day-hike', 'backpacking', 'multi-day']),
    trailStatus: z.enum(['official', 'mixed', 'off-trail']),
    trailStatusDisplay: z.string().min(1),
    shape: z.enum(['loop', 'out-and-back', 'point-to-point']),
    distanceMi: z.number().positive(),
    estimatedDuration: z.string().nullable(),
    physicalDifficulty: z.string().min(1),
    physicalDifficultyDetail: z.string().min(1),
    navigationDifficulty: z.string().min(1),
    navigationDifficultyDetail: z.string().min(1),
    lastPersonallyTraveled: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    lastInformationReview: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    accessParking: z.string().min(1),
    hazards: z.array(z.string().min(1)),
    waterCamping: z.array(z.string().min(1)),
    landAccessReview: z.string().min(1),
    publicWaypoints: z.array(waypointSchema),
    relatedContent: z.array(z.object({ label: z.string(), href: z.string() })),
    approvedPublicationGpx: publicArtifactSchema.extend({
      trackPointCount: z.number().int().positive(),
      waypointCount: z.number().int().nonnegative()
    }),
    webGeometry: publicArtifactSchema,
    elevation: z.object({
      publicPath: z.string().startsWith('/data/routes/'),
      sourceId: z.literal('usgs-3dep-bare-earth-dem'),
      sampleCount: z.number().int().min(2).max(1000),
      method: z.string().min(1),
      generatedAtBuild: z.literal(true)
    }),
    landManagerResources: z.array(z.object({
      label: z.string().min(1),
      href: z.string().url()
    })).min(1),
    sourceDependencyIds: z.array(z.string().min(1)).min(1)
  })
});

export const collections = { routes };

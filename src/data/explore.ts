import { stories } from './stories';

export interface ExploreLink {
  label: string;
  href: string;
  external?: boolean;
  download?: boolean;
  note?: string;
}

export interface ExploreSection {
  slug: string;
  title: string;
  description: string;
  links: ExploreLink[];
}

export const exploreSections: ExploreSection[] = [
  {
    slug: 'stories',
    title: 'Stories',
    description: 'First-hand RRGH stories from the Gorge, Clifty Wilderness, and the Sheltowee Trace.',
    links: [
      ...stories.map((story) => ({ label: story.title, href: `/stories/${story.slug}/` })),
      { label: 'View All Stories', href: '/stories/' }
    ]
  },
  {
    slug: 'search-and-rescue',
    title: 'Search & Rescue',
    description: 'Regional rescue context, preparedness, and the Wolfe County team RRGH supports.',
    links: [
      { label: 'Search & Rescue overview', href: '/search-and-rescue/' },
      { label: 'Wolfe County Search & Rescue', href: 'https://wcsart.com/', external: true },
      { label: 'Powell County Search & Rescue', href: 'https://www.pocosar.org/', external: true },
      { label: 'Kentucky Emergency Management — Search & Rescue', href: 'https://www.kyem.ky.gov/operations-programs/search-and-rescue', external: true },
      { label: 'Hiking preparedness & safety', href: '/search-and-rescue/#prep-title' },
      { label: 'Donate directly to Wolfe County SAR', href: 'https://wcsart.com/donate/', external: true }
    ]
  },
  {
    slug: 'camping',
    title: 'Camping',
    description: 'RRGH’s camping guide plus current Forest Service visitor information and rules context.',
    links: [
      { label: '2026 DBNF Dispersed Camping Guide', href: '/search-and-rescue/#camping-title' },
      { label: 'Download Guide', href: '/downloads/red-river-gorge-hiker-2026-dbnf-dispersed-camping-guide.pdf', download: true },
      { label: 'Daniel Boone National Forest alerts & notices', href: 'https://www.fs.usda.gov/alerts/dbnf/alerts-notices/?aid=77606', external: true },
      { label: 'Gladie Visitor Center', href: 'https://www.fs.usda.gov/r08/danielboone/recreation/gladie-visitor-center', external: true }
    ]
  },
  {
    slug: 'landforms',
    title: 'Landforms',
    description: 'Independent reference sites for arches, waterfalls, overlooks, and other Kentucky landforms.',
    links: [
      { label: 'Arches of the Red River Gorge — William H. Patrick', href: 'https://redrivergorgearches.com/', external: true },
      { label: 'Kentucky Arches', href: 'https://kyarches.com/', external: true },
      { label: 'Kentucky Waterfalls', href: 'https://kywaterfalls.com/', external: true },
      { label: 'Kentucky Overlooks', href: 'https://kyoverlooks.com/', external: true },
      { label: 'Kentucky Landforms', href: 'https://kylandforms.com/', external: true }
    ]
  },
  {
    slug: 'trails',
    title: 'Trails',
    description: 'Authoritative and established trail-planning resources for the Gorge and surrounding country.',
    links: [
      { label: 'Sheltowee Trace Association', href: 'https://sheltoweetrace.org/', external: true },
      { label: 'Daniel Boone National Forest Maps & Guides', href: 'https://www.fs.usda.gov/r08/danielboone/maps-guides', external: true },
      { label: 'Clifty Wilderness', href: 'https://www.fs.usda.gov/r08/danielboone/recreation/clifty-wilderness', external: true }
    ]
  },
  {
    slug: 'maps-and-guides',
    title: 'Maps & Guides',
    description: 'Land-manager maps, visitor information, and park resources.',
    links: [
      { label: 'Daniel Boone National Forest Maps & Guides', href: 'https://www.fs.usda.gov/r08/danielboone/maps-guides', external: true },
      { label: 'Clifty Wilderness', href: 'https://www.fs.usda.gov/r08/danielboone/recreation/clifty-wilderness', external: true },
      { label: 'Gladie Visitor Center', href: 'https://www.fs.usda.gov/r08/danielboone/recreation/gladie-visitor-center', external: true },
      { label: 'Natural Bridge State Resort Park', href: 'https://parks.ky.gov/explore/natural-bridge-state-resort-park-7796', external: true }
    ]
  },
  {
    slug: 'current-conditions',
    title: 'Current Conditions',
    description: 'Go to the governing source for closures, weather, roads, and park notices.',
    links: [
      { label: 'Daniel Boone National Forest alerts & closures', href: 'https://www.fs.usda.gov/alerts/dbnf/alerts-notices/?aid=77606', external: true },
      { label: 'National Weather Service — Slade area', href: 'https://forecast.weather.gov/MapClick.php?lat=37.783&lon=-83.683', external: true },
      { label: 'GoKY road conditions', href: 'https://goky.ky.gov/', external: true },
      { label: 'Natural Bridge / Kentucky State Parks notices', href: 'https://parks.ky.gov/explore/natural-bridge-state-resort-park-7796', external: true }
    ]
  },
  {
    slug: 'hiking-safety',
    title: 'Hiking Safety',
    description: 'RRGH preparedness guidance and established National Park Service safety resources.',
    links: [
      { label: 'RRGH preparedness section', href: '/search-and-rescue/#prep-title' },
      { label: 'NPS Ten Essentials', href: 'https://www.nps.gov/articles/10essentials.htm', external: true },
      { label: 'NPS Hike Smart', href: 'https://www.nps.gov/articles/hiking-safety.htm', external: true }
    ]
  }
];

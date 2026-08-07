export const LOCATION = 'Clifty Wilderness, Red River Gorge, Kentucky' as const;
export const VERIFICATION_DATE = '2026-08-06' as const;
export const PUZZLE = {
  dimensions: '18 × 24 inches',
  pieceCount: 500,
  orientation: 'Horizontal',
  customerPrice: '$59.99 before shipping and tax',
  artistMarkup: '$24.99',
  merchandise: 'puzzle'
} as const;

export type Orientation = 'Landscape' | 'Portrait' | 'Panorama' | 'Square';

export interface Photograph {
  catalogId: string;
  displayOrder: number;
  title: string;
  slug: string;
  location: typeof LOCATION;
  captureDate: string;
  orientation: Orientation;
  contextLine: string;
  shortDescription: string;
  story: string;
  altText: string;
  wallArtUrl: string;
  wallArtAvailable: true;
  puzzleAvailable: boolean;
  puzzleUrl?: string;
  puzzleDimensions?: typeof PUZZLE.dimensions;
  puzzlePieceCount?: typeof PUZZLE.pieceCount;
  puzzleOrientation?: typeof PUZZLE.orientation;
  puzzleCustomerPrice?: typeof PUZZLE.customerPrice;
  puzzleSummary?: string;
  productStatusNote: string;
  productVerificationDate: typeof VERIFICATION_DATE;
  sourceFilename: string;
}

const common = {
  location: LOCATION,
  wallArtAvailable: true as const,
  productVerificationDate: VERIFICATION_DATE
};

export const photographs: readonly Photograph[] = [
  {
    ...common,
    catalogId: 'RRGH-0001',
    displayOrder: 1,
    title: 'Double Rainbow at Eagle’s Point Buttress',
    slug: 'double-rainbow-at-eagles-point-buttress',
    captureDate: 'July 19, 2025',
    orientation: 'Panorama',
    contextLine: 'Clifty Wilderness, Red River Gorge, Kentucky · Summer storm · Signature panorama',
    shortDescription: 'After a heavy summer rain, a brilliant double rainbow appeared over the Red River Gorge from Eagle’s Point Buttress Overlook. Already preparing for a Sheltowee Trace thru-hike, Ryan experienced the moment as assurance that he would be able to complete the journey.',
    story: 'On July 19, 2025, Ryan camped near Eagle’s Point Buttress while testing gear for a Sheltowee Trace thru-hike he was already preparing to undertake. The evening was extremely hot and rainy. After a heavy rain, during which he kept a campfire going and watched a group of hikers descend the mountain, the weather cleared quickly. Ryan called home to say goodnight to his daughter Lilianna and was speaking with his partner Charlee as he walked onto the lower overlook. A brilliant double rainbow appeared over the clearing landscape, and Charlee urged him to get off the phone and photograph it. Ryan regards the resulting panorama as his signature image. He experienced the rainbow not as a call to begin the Sheltowee Trace, but as a deeply personal assurance that he would be able to complete the journey he had already chosen and was preparing for. He later completed the thru-hike. The photograph is intended for a special physical display at The Hungry Hiker, but it has not yet been printed or delivered.',
    altText: 'Double rainbow above foggy forested ridges, photographed from Eagle’s Point Buttress Overlook after a summer storm.',
    wallArtUrl: 'https://fineartamerica.com/featured/double-rainbow-at-eagles-point-buttress-ryan-d-lewis.html',
    puzzleAvailable: false,
    productStatusNote: 'Signature panorama. Wall art only at launch.',
    sourceFilename: 'RRGH-0001-Double_Rainbow_at_Eagles_Point_Buttress-WEB-WM.webp'
  },
  {
    ...common,
    catalogId: 'RRGH-0004',
    displayOrder: 2,
    title: 'Winter at Red-byrd Arch',
    slug: 'winter-at-red-byrd-arch',
    captureDate: 'January 23, 2024',
    orientation: 'Landscape',
    contextLine: 'Clifty Wilderness, Red River Gorge, Kentucky · Winter snow and ice',
    shortDescription: 'A towering ice formation rises beneath the sandstone at Red-byrd Arch after unusually severe snow and freezing conditions in the Red River Gorge.',
    story: 'On January 23, 2024, Ryan and his cousin chose a spontaneous snowy day hike after Ryan’s unsuccessful backpacking attempt along Swift Camp Creek. Both had visited Red-byrd Arch before and approached from the Calaboose Ridge Road side using prior knowledge, maps, and a very faint trace rather than a formal trail. The ice and snow were unusually severe, and they used a short rappel to descend an icy section. Ryan remembers the fun outing and rappel with his cousin.',
    altText: 'Large layered ice column beneath the sandstone at Red-byrd Arch, surrounded by snow-covered rocks and winter forest.',
    wallArtUrl: 'https://fineartamerica.com/featured/winter-at-red-byrd-arch-ryan-d-lewis.html',
    puzzleAvailable: true,
    puzzleUrl: 'https://fineartamerica.com/featured/winter-at-red-byrd-arch-ryan-d-lewis.html?product=puzzle',
    puzzleDimensions: PUZZLE.dimensions,
    puzzlePieceCount: PUZZLE.pieceCount,
    puzzleOrientation: PUZZLE.orientation,
    puzzleCustomerPrice: PUZZLE.customerPrice,
    puzzleSummary: 'Severe snow and freezing conditions created a towering ice formation beneath the sandstone at Red-byrd Arch, turning a familiar feature into a deep-winter scene.',
    productStatusNote: 'Wall art and approved puzzle.',
    sourceFilename: 'RRGH-0004-Winter_at_Red-byrd_Arch-WEB-WM.webp'
  },
  {
    ...common,
    catalogId: 'RRGH-0005',
    displayOrder: 3,
    title: 'Sunrise at Eagle’s Nest',
    slug: 'sunrise-at-eagles-nest',
    captureDate: 'December 21, 2025',
    orientation: 'Landscape',
    contextLine: 'Clifty Wilderness, Red River Gorge, Kentucky · Clear winter sunrise',
    shortDescription: 'A vivid winter sunrise illuminates the horizon beside the sandstone hueco known as Eagle’s Nest. After arriving, Ryan chose a different campsite than usual, which gave him a better view of the morning sky.',
    story: 'On December 21, 2025, Ryan led three friends on a hike to Copperas Falls. After they departed, he continued to Eagle’s Nest and camped overnight. He already knew the hueco known as Eagle’s Nest. Once he arrived, he chose a different campsite than usual, a choice made in the moment that offered a better sunrise vantage than his customary site. The next morning, he traversed west from Eagle’s Point Buttress Overlook along the ridge top and cliff edge and photographed an exceptionally vibrant sunrise from that improved position. The morning was chilly, clear, and pleasant. Ryan was alone for the sunrise and remembers it as the most vivid sunrise he had personally seen.',
    altText: 'Vivid orange sunrise beside the sandstone at Eagle’s Nest, overlooking forested ridges and a river in the Red River Gorge.',
    wallArtUrl: 'https://fineartamerica.com/featured/sunrise-at-eagles-nest-ryan-d-lewis.html',
    puzzleAvailable: true,
    puzzleUrl: 'https://fineartamerica.com/featured/sunrise-at-eagles-nest-ryan-d-lewis.html?product=puzzle',
    puzzleDimensions: PUZZLE.dimensions,
    puzzlePieceCount: PUZZLE.pieceCount,
    puzzleOrientation: PUZZLE.orientation,
    puzzleCustomerPrice: PUZZLE.customerPrice,
    puzzleSummary: 'A different campsite offered a better view of the morning sky and led to the most vivid sunrise Ryan had personally seen.',
    productStatusNote: 'Wall art and approved puzzle.',
    sourceFilename: 'RRGH-0005-Sunrise_at_Eagles_Nest-WEB-WM.webp'
  },
  {
    ...common,
    catalogId: 'RRGH-0002',
    displayOrder: 4,
    title: 'Dog Fork Falls in Winter',
    slug: 'dog-fork-falls-in-winter',
    captureDate: 'February 22, 2025',
    orientation: 'Square',
    contextLine: 'Clifty Wilderness, Red River Gorge, Kentucky · Late-winter thaw · Square composition',
    shortDescription: 'Snow, flowing water, and long icicles surround Dog Fork Falls during the final weeks of winter in the Clifty Wilderness.',
    story: 'On February 22, 2025, Ryan led friends to Dog Fork Falls after the last snow of the season. He photographed the waterfall from a position directly south of it on the Dog Fork tributary leading into Swift Camp Creek. While exploring the remote area, the group followed the nearest ridge before descending to the falls and tributary. Temperatures were near freezing, approximately 35 to 40 degrees, but the approach was not exceptionally difficult. The memorable part was sharing a remote off-trail winter waterfall with friends as snow, long icicles, and flowing water marked the transition toward spring.',
    altText: 'Dog Fork Falls surrounded by long icicles, snow-covered sandstone, flowing water, and rhododendron in winter.',
    wallArtUrl: 'https://fineartamerica.com/featured/dog-fork-falls-in-winter-ryan-d-lewis.html',
    puzzleAvailable: false,
    productStatusNote: 'Wall art only at launch. Square composition is not offered in the fixed puzzle format.',
    sourceFilename: 'RRGH-0002-Dog_Fork_Falls_in_Winter-WEB-WM.webp'
  },
  {
    ...common,
    catalogId: 'RRGH-0007',
    displayOrder: 5,
    title: 'Ice at West of Copperas Pillar',
    slug: 'ice-at-west-of-copperas-pillar',
    captureDate: 'February 23, 2025',
    orientation: 'Landscape',
    contextLine: 'Clifty Wilderness, Red River Gorge, Kentucky · Final winter thaw',
    shortDescription: 'Long icicles frame West of Copperas Pillar during the final winter thaw, as lingering snow and ice disappear from the Red River Gorge.',
    story: 'On February 23, 2025, after spending a cold night with friends beside a warm campfire, Ryan led a day hike to several remote features that some members of the group had not seen before. The party included Ryan, Dan, Scott, Bill, and Dan’s son. Their destinations included West of Copperas Pillar, Scooter Arch, a small cave, and a vantage point of Sky Bridge. They began near the unofficial and barely traced Hopewell Arch Trail, then quickly left it for trail-less terrain. Temperatures rose to approximately 50 degrees as the season’s final snow and ice thawed rapidly. The long, extensive icicles at West of Copperas Pillar were likely more pronounced than under ordinary winter conditions because they were photographed during this final thaw.',
    altText: 'Long icicles hanging beneath sandstone beside West of Copperas Pillar, surrounded by snow, rhododendron, and winter forest.',
    wallArtUrl: 'https://fineartamerica.com/featured/ice-at-west-of-copperas-pillar-ryan-d-lewis.html',
    puzzleAvailable: true,
    puzzleUrl: 'https://fineartamerica.com/featured/ice-at-west-of-copperas-pillar-ryan-d-lewis.html?product=puzzle',
    puzzleDimensions: PUZZLE.dimensions,
    puzzlePieceCount: PUZZLE.pieceCount,
    puzzleOrientation: PUZZLE.orientation,
    puzzleCustomerPrice: PUZZLE.customerPrice,
    puzzleSummary: 'Long icicles were photographed during the final winter thaw as temperatures climbed and the season’s last snow and ice disappeared.',
    productStatusNote: 'Wall art and approved puzzle.',
    sourceFilename: 'RRGH-0007-Ice_at_West_of_Copperas_Pillar-WEB-WM.webp'
  },
  {
    ...common,
    catalogId: 'RRGH-0003',
    displayOrder: 6,
    title: 'Splatter Falls',
    slug: 'splatter-falls',
    captureDate: 'April 13, 2024',
    orientation: 'Portrait',
    contextLine: 'Clifty Wilderness, Red River Gorge, Kentucky · Original discovery · Portrait composition',
    shortDescription: 'A remote four-drop cascade descends through layered sandstone before splattering into an amber pool. Ryan discovered, measured, documented, and named Splatter Falls during an off-trail exploration.',
    story: 'Ryan discovered Splatter Falls on April 13, 2024, while exploring remote cliff-line drainages for waterfalls. The small watershed made the falls unexpected, but a broad cut in the upper rock ledge suggested dependable spring flow. This was his original discovery and only visit so far. Alone, he measured and documented the four-drop cascade and named it Splatter Falls for the pronounced splatter between its middle drops before the water reaches the lower pool.',
    altText: 'Splatter Falls descending through four sandstone drops into an amber pool in the Red River Gorge.',
    wallArtUrl: 'https://fineartamerica.com/featured/splatter-falls-ryan-d-lewis.html',
    puzzleAvailable: false,
    productStatusNote: 'Wall art only at launch. Narrow vertical composition is not offered in the fixed puzzle format.',
    sourceFilename: 'RRGH-0003-Splatter_Falls-WEB-WM.webp'
  }
] as const;

export const bySlug = (slug: string) => photographs.find((photo) => photo.slug === slug);

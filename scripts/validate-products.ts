import { photographs, PUZZLE } from '../src/data/products.ts';

const fail = (message: string): never => {
  throw new Error(message);
};

if (photographs.length !== 6) fail('Exactly six launch photographs are required.');

const orders = photographs.map((photo) => photo.displayOrder);
if (new Set(orders).size !== photographs.length) fail('Display orders must be unique.');
if (orders.join(',') !== '1,2,3,4,5,6') fail('Display order must be exactly one through six.');

if (photographs.some((photo) => /sunset|RRGH-0006/i.test(`${photo.catalogId} ${photo.title} ${photo.slug} ${photo.sourceFilename}`))) {
  fail('Prohibited sunset photograph detected.');
}

for (const photo of photographs) {
  const requiredText = {
    title: photo.title,
    slug: photo.slug,
    captureDate: photo.captureDate,
    contextLine: photo.contextLine,
    shortDescription: photo.shortDescription,
    story: photo.story,
    altText: photo.altText,
    productStatusNote: photo.productStatusNote,
    sourceFilename: photo.sourceFilename,
    productVerificationDate: photo.productVerificationDate
  };

  for (const [field, value] of Object.entries(requiredText)) {
    if (!value.trim()) fail(`Missing ${field}: ${photo.catalogId}`);
  }

  if (!photo.wallArtAvailable || !photo.wallArtUrl) {
    fail(`Every launch photograph requires wall art: ${photo.catalogId}`);
  }
}

const puzzles = photographs.filter((photo) => photo.puzzleAvailable);
if (puzzles.length !== 3) fail('Exactly three puzzles are required.');

const approvedPuzzleIds = ['RRGH-0004', 'RRGH-0005', 'RRGH-0007'];
if (puzzles.map((photo) => photo.catalogId).join(',') !== approvedPuzzleIds.join(',')) {
  fail('Puzzle availability does not match the approved photographs.');
}

for (const photo of puzzles) {
  if (
    !photo.puzzleUrl ||
    !photo.puzzleSummary ||
    photo.puzzleDimensions !== PUZZLE.dimensions ||
    photo.puzzlePieceCount !== PUZZLE.pieceCount ||
    photo.puzzleOrientation !== PUZZLE.orientation ||
    photo.puzzleCustomerPrice !== PUZZLE.customerPrice
  ) {
    fail(`Invalid puzzle configuration: ${photo.catalogId}`);
  }
}

if (photographs.some((photo) => Object.keys(photo).some((key) => /card|shirt|mug|merchandise/i.test(key)))) {
  fail('Unsupported merchandise detected.');
}

console.log('Product data and approved photograph content validation passed.');

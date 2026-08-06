import { photographs, PUZZLE } from '../src/data/products.ts';
const fail = (message: string): never => { throw new Error(message); };
if (photographs.length !== 6) fail('Exactly six launch photographs are required.');
if (new Set(photographs.map(p => p.displayOrder)).size !== photographs.length) fail('Display orders must be unique.');
if (photographs.some(p => /sunset/i.test(`${p.title} ${p.slug} ${p.sourceFilename}`))) fail('Prohibited sunset photograph detected.');
if (photographs.some(p => !p.wallArtAvailable || !p.wallArtUrl)) fail('Every launch photograph requires wall art.');
const puzzles = photographs.filter(p => p.puzzleAvailable);
if (puzzles.length !== 3) fail('Exactly three puzzles are required.');
for (const p of puzzles) {
 if (!p.puzzleUrl || p.puzzleDimensions !== PUZZLE.dimensions || p.puzzlePieceCount !== PUZZLE.pieceCount || p.puzzleOrientation !== PUZZLE.orientation || p.puzzleCustomerPrice !== PUZZLE.customerPrice) fail(`Invalid puzzle configuration: ${p.catalogId}`);
}
if (photographs.some(p => Object.keys(p).some(k => /card|shirt|mug|merchandise/i.test(k)))) fail('Unsupported merchandise detected.');
console.log('Product data validation passed.');

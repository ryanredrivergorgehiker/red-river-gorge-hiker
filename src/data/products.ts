export const LOCATION = 'Clifty Wilderness, Red River Gorge, Kentucky' as const;
export const VERIFICATION_DATE = '2026-08-06' as const;
export const PUZZLE = { dimensions: '18 × 24 inches', pieceCount: 500, orientation: 'Horizontal', customerPrice: '$59.99 before shipping and tax', artistMarkup: '$24.99', merchandise: 'puzzle' } as const;
export type Orientation = 'Landscape' | 'Portrait' | 'Panorama' | 'Square';
export interface Photograph {
  catalogId: string; displayOrder: number; title: string; slug: string; location: typeof LOCATION;
  orientation: Orientation; wallArtUrl: string; wallArtAvailable: true; puzzleAvailable: boolean;
  puzzleUrl?: string; puzzleDimensions?: typeof PUZZLE.dimensions; puzzlePieceCount?: typeof PUZZLE.pieceCount;
  puzzleOrientation?: typeof PUZZLE.orientation; puzzleCustomerPrice?: typeof PUZZLE.customerPrice;
  productVerificationDate: typeof VERIFICATION_DATE; sourceFilename: string;
}
const common = { location: LOCATION, wallArtAvailable: true as const, productVerificationDate: VERIFICATION_DATE };
export const photographs: readonly Photograph[] = [
 { ...common, catalogId:'RRGH-0001', displayOrder:1, title:'Double Rainbow at Eagle’s Point Buttress', slug:'double-rainbow-at-eagles-point-buttress', orientation:'Panorama', wallArtUrl:'https://fineartamerica.com/featured/double-rainbow-at-eagles-point-buttress-ryan-d-lewis.html', puzzleAvailable:false, sourceFilename:'RRGH-0001-Double_Rainbow_at_Eagles_Point_Buttress-WEB-WM.webp' },
 { ...common, catalogId:'RRGH-0004', displayOrder:2, title:'Winter at Red-byrd Arch', slug:'winter-at-red-byrd-arch', orientation:'Landscape', wallArtUrl:'https://fineartamerica.com/featured/winter-at-red-byrd-arch-ryan-d-lewis.html', puzzleAvailable:true, puzzleUrl:'https://fineartamerica.com/featured/winter-at-red-byrd-arch-ryan-d-lewis.html?product=puzzle', puzzleDimensions:PUZZLE.dimensions, puzzlePieceCount:PUZZLE.pieceCount, puzzleOrientation:PUZZLE.orientation, puzzleCustomerPrice:PUZZLE.customerPrice, sourceFilename:'RRGH-0004-Winter_at_Red-byrd_Arch-WEB-WM.webp' },
 { ...common, catalogId:'RRGH-0005', displayOrder:3, title:'Sunrise at Eagle’s Nest', slug:'sunrise-at-eagles-nest', orientation:'Landscape', wallArtUrl:'https://fineartamerica.com/featured/sunrise-at-eagles-nest-ryan-d-lewis.html', puzzleAvailable:true, puzzleUrl:'https://fineartamerica.com/featured/sunrise-at-eagles-nest-ryan-d-lewis.html?product=puzzle', puzzleDimensions:PUZZLE.dimensions, puzzlePieceCount:PUZZLE.pieceCount, puzzleOrientation:PUZZLE.orientation, puzzleCustomerPrice:PUZZLE.customerPrice, sourceFilename:'RRGH-0005-Sunrise_at_Eagles_Nest-WEB-WM.webp' },
 { ...common, catalogId:'RRGH-0002', displayOrder:4, title:'Dog Fork Falls in Winter', slug:'dog-fork-falls-in-winter', orientation:'Portrait', wallArtUrl:'https://fineartamerica.com/featured/dog-fork-falls-in-winter-ryan-d-lewis.html', puzzleAvailable:false, sourceFilename:'RRGH-0002-Dog_Fork_Falls_in_Winter-WEB-WM.webp' },
 { ...common, catalogId:'RRGH-0007', displayOrder:5, title:'Ice at West of Copperas Pillar', slug:'ice-at-west-of-copperas-pillar', orientation:'Landscape', wallArtUrl:'https://fineartamerica.com/featured/ice-at-west-of-copperas-pillar-ryan-d-lewis.html', puzzleAvailable:true, puzzleUrl:'https://fineartamerica.com/featured/ice-at-west-of-copperas-pillar-ryan-d-lewis.html?product=puzzle', puzzleDimensions:PUZZLE.dimensions, puzzlePieceCount:PUZZLE.pieceCount, puzzleOrientation:PUZZLE.orientation, puzzleCustomerPrice:PUZZLE.customerPrice, sourceFilename:'RRGH-0007-Ice_at_West_of_Copperas_Pillar-WEB-WM.webp' },
 { ...common, catalogId:'RRGH-0003', displayOrder:6, title:'Splatter Falls', slug:'splatter-falls', orientation:'Portrait', wallArtUrl:'https://fineartamerica.com/featured/splatter-falls-ryan-d-lewis.html', puzzleAvailable:false, sourceFilename:'RRGH-0003-Splatter_Falls-WEB-WM.webp' }
] as const;
export const bySlug = (slug: string) => photographs.find((photo) => photo.slug === slug);

"""No-network synthetic integrity regressions for KyTopo source receipt replay."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from verify_kytopo_qa_receipts import verify, jpeg_dimensions

# Structural JPEG marker fixture, NOT a decoded raster or original map image.
SAMPLE = b'\xff\xd8\xff\xc0\x00\x11\x08\x01\x00\x01\x00\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00' + b'0'*64 + b'\xff\xd9'


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.dest=Path(temp.name)/'source.zip'
        ids=['N13E29','N13E30']
        self.name='N13E29__N13E30/kentucky-topo/16/17535/25302.jpg'
        sources={f'N{n}E{e}':{'url':f'https://official.example/{n}_{e}.tif',
                              'originalFileBytes':8_000_000}
                 for n in (13,14,15) for e in (29,30,31)}
        self.plan={'status':'SOURCE FOOTPRINT PLAN ONLY — REAL IMAGE PIXELS UNVERIFIED',
                   'allActualPixelsCovered':False,'fullOfflineHikingPackComplete':False,
                   'sourceCatalog':sources,'totalCandidateTiles':1,
                   'levels':[{'zoom':16,'expectedTiles':1}],
                   'plannedTiles':[{'z':16,'x':17535,'y':25302,
                                    'sourceIds':ids,'sourceBboxUnionCoversClippedTile':True}]}
        self.rec={'pair':ids,'xyz':{'z':16,'x':17535,'y':25302},
                  'sources':[{'id':i,'url':sources[i]['url'],'length':8_000_000} for i in ids],
                  'sourcePixelAlpha':[{'id':i,'alphaMax':255} for i in ids],
                  'mosaicAlphaMin':255,'mosaicAlphaMax':255,
                  'geoQA':{'pixelAndGeographicAlignmentVerified':True,
                           'pixelSizeEPSG3857':40075016.68557849/(65536*256),
                           'rgbStddev':[12,14,16]},
                  'sourceBytesTransferred':333333,'httpRangeRequests':4,
                  'jpegPath':self.name,'jpegSha256':hashlib.sha256(SAMPLE).hexdigest(),
                  'jpegBytes':len(SAMPLE)}

    def archive(self, image=SAMPLE):
        report={'candidateCount':1,'records':[self.rec],'notCustomerReady':True,
                'completeGorgePixelCoverage':False,'finalCoreDownloadBytes':None,
                'originalWholeTiffsDownloaded':False,
                'originalBytesTransferred':self.rec['sourceBytesTransferred']}
        with zipfile.ZipFile(self.dest,'w') as z:
            z.writestr('TWELVE-SOURCE-BOUNDARY-PILOT.json',json.dumps(report))
            z.writestr(self.name,image)
        return self.dest

    def test_one_receipt_cannot_be_full_regional_coverage(self):
        self.assertEqual(jpeg_dimensions(SAMPLE),(256,256))
        report=verify(self.plan,[self.archive()])
        self.assertEqual(report['sourceQaReceiptCount'],1)
        self.assertFalse(report['fullGorgePixelCoverage'])
        self.assertIsNone(report['downloadBytes'])

    def test_hash_tamper_rejected(self):
        image=SAMPLE[:50]+b'X'+SAMPLE[51:]
        with self.assertRaisesRegex(ValueError,'hash disagreement'):
            verify(self.plan,[self.archive(image)])

    def test_original_source_tamper_rejected(self):
        self.rec['sources'][0]['url']='https://other.example/false.tif'
        with self.assertRaisesRegex(ValueError,'original URL'):
            verify(self.plan,[self.archive()])

    def test_transparent_mosaic_rejected(self):
        self.rec['mosaicAlphaMin']=0
        with self.assertRaisesRegex(ValueError,'alpha/geographic'):
            verify(self.plan,[self.archive()])

    def test_gap_in_plan_rejected(self):
        self.plan['plannedTiles'][0]['sourceBboxUnionCoversClippedTile']=False
        with self.assertRaisesRegex(ValueError,'uncovered rectangle'):
            verify(self.plan,[self.archive()])

    def test_duplicate_archive_rejected(self):
        a=self.archive()
        with self.assertRaisesRegex(ValueError,'duplicate region QA tile'):
            verify(self.plan,[a,a])

    def test_unverified_additional_tile_remains_open(self):
        rec=copy.deepcopy(self.plan['plannedTiles'][0]);rec['y']=25303
        self.plan['plannedTiles'].append(rec)
        self.plan['totalCandidateTiles']=2
        result=verify(self.plan,[self.archive()])
        self.assertEqual(result['remainingWithoutReceipts'],1)
        self.assertFalse(result['corePackageReady'])


if __name__=='__main__':
    unittest.main()

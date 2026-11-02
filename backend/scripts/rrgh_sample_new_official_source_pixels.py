#!/usr/bin/env python3
"""Bounded public COG pixel sample QA. Does not authorize production or full coverage.

Only reads a few public Kentucky source pixels from gaps in original pinned
source metadata; preserves all original sources, immutable receipts, and
private map input boundaries. No GCP connection and no downloads to package.
"""
import argparse
import base64
import json
import math
from pathlib import Path
import zlib

import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.warp import transform

from rrgh_audit_expanded_official_sources import BOUNDS, xy, window, intersects


def samples(catalog, region, *, per_layer):
    old=region["inventory"]["sources"]
    sources=catalog["catalog"]
    left,bottom=xy(BOUNDS[0],BOUNDS[1],16)
    right,top=xy(BOUNDS[2],BOUNDS[3],16)
    result=[]
    for layer in ("hiking","terrain","leaf-off"):
        fam="dem" if layer=="terrain" else layer
        prev=old[fam]
        new=sources[fam]
        used=set()
        eligible=[]
        for x in range(left,right+1):
            for y in range(top,bottom+1):
                rect=window(16,x,y,1/512 if layer=="terrain" else 0)
                if any(intersects(s["bbox"],rect) for s in prev):
                    continue
                current=[s for s in new if intersects(
                    s.get("boundsWGS84",s.get("bbox")),rect) and s["id"] not in used]
                if current:
                    eligible.append((x,y,current))
        if len(eligible)<per_layer:
            raise ValueError("Insufficient distinct uncovered samples for "+layer)
        interval=max(1,len(eligible)//per_layer)
        for x,y,group in eligible[::interval]:
            item=next((s for s in group if s["id"] not in used),None)
            if item is None:
                continue
            used.add(item["id"])
            rect=window(16,x,y)
            b=item.get("boundsWGS84",item.get("bbox"))
            intersection=(max(rect[0],b[0]),max(rect[1],b[1]),
                          min(rect[2],b[2]),min(rect[3],b[3]))
            if intersection[0]>=intersection[2] or intersection[1]>=intersection[3]:
                continue
            result.append({"layer":layer,"id":item["id"],
                           "url":item.get("officialOriginalCogURL",item.get("officialCogURL")),
                           "lon":(intersection[0]+intersection[2])/2,
                           "lat":(intersection[1]+intersection[3])/2,
                           "z16":f"{x}-{y}"})
            if len(used)>=per_layer:
                break
        if len(used)!=per_layer:
            raise ValueError("Could not choose independent source samples: "+layer)
    return result


def inspect(entry):
    url=entry["url"]
    if not url.startswith("https://kyfromabove.s3.us-west-2.amazonaws.com/") or not url.endswith(".tif"):
        raise ValueError("Unexpected public source host or asset extension")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_MAX_RETRY="0",
                      GDAL_HTTP_TIMEOUT="20",
                      GDAL_CACHEMAX=32000000):
        with rasterio.open("/vsicurl/"+url) as ds:
            required_bands=1 if entry["layer"]=="terrain" else 3
            if not ds.crs or ds.count<required_bands:
                raise ValueError("Missing projected CRS or required channels")
            if not ds.crs.is_projected:
                raise ValueError("Source has unexpected geographic coordinates")
            native_x,native_y=transform("EPSG:4326",ds.crs,[entry["lon"]],[entry["lat"]])
            row,col=ds.index(native_x[0],native_y[0])
            row=max(0,min(ds.height-1,row))
            col=max(0,min(ds.width-1,col))
            win=Window(max(0,col-12),max(0,row-12),
                       min(24,ds.width-max(0,col-12)),
                       min(24,ds.height-max(0,row-12)))
            bands=ds.read(list(range(1,required_bands+1)),window=win,masked=True)
            if bands.size==0:
                raise ValueError("Empty exact original source pixel sample")
            mask=np.ma.getmaskarray(bands)
            data=np.ma.getdata(bands)
            valid=(~mask).all(axis=0)&np.isfinite(data).all(axis=0)
            if not valid.any():
                raise ValueError("Original source sample has zero valid native pixels")
            return {**{k:entry[k] for k in ("layer","id","z16")},
                    "crs":str(ds.crs),"width":ds.width,"height":ds.height,
                    "bands":ds.count,"units":list(ds.units),
                    "sampleValidFraction":round(float(valid.mean()),6),
                    "samplePixels":int(valid.size),
                    "sampleValidPixels":int(valid.sum()),
                    "sampleHasFiniteNumericValues":True,
                    "fullWindowPixelCoverageProved":False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--catalog",required=True,type=Path)
    parser.add_argument("--region",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--per-layer",type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.per_layer<=5:
        raise SystemExit("Per-layer public source sample limit is 1..5")
    catalog=json.loads(args.catalog.read_bytes())
    region=json.loads(zlib.decompress(base64.b64decode(args.region.read_bytes())))
    chosen=samples(catalog,region,per_layer=args.per_layer)
    results=[];errors=[]
    for entry in chosen:
        try:
            row=inspect(entry)
            results.append(row)
            print("OFFICIAL_COG_SAMPLE_PASS",json.dumps(row,sort_keys=True),flush=True)
        except Exception as ex:
            failures={"layer":entry["layer"],"id":entry["id"],"errorClass":type(ex).__name__}
            errors.append(failures)
            print("OFFICIAL_COG_SAMPLE_FAIL",json.dumps(failures,sort_keys=True),flush=True)
    report={"format":"rrgh-bounded-official-new-source-native-pixel-sample-v1",
            "candidatesAttempted":len(chosen),"samplesVerified":results,"samplesFailed":errors,
            "fullRegionalPixelsValidated":False,"productionPromotionApproved":False,
            "newLicenseTermsCertified":False,"originalAcceptedCachesModified":False}
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    if errors:raise SystemExit("One or more official source samples failed; inspect report")
    print("RRGH_NEW_OFFICIAL_NATIVE_PIXEL_SAMPLES_PASS__NOT_REGIONAL_QA")


if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""Bounded, genuine twelve-source-boundary Kentucky Topo raster QA.

Each original COG read via strict localhost HTTP206 proxies, not full TIFF
downloads. Pixel closure and CRS verified independently for each 256px
derived tile. This is PRIVATE QA, never an installable Core/Base package.
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Thread

from pilot_official_cog_xyz import (
    HOST, RangeBudget, mercator_bounds, proxy_handler, verify_derived_grid,
)
from pilot_ky_topo_original_xyz import source
from plan_kytopo_quad_seams import plan

PER_SEAM_MAX = 5_000_000
ALL_MAX = 60_000_000


def environ():
    return dict(os.environ,
                GDAL_DISABLE_READDIR_ON_OPEN="YES",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                CPL_VSIL_CURL_USE_HEAD="YES",
                CPL_VSIL_CURL_CHUNK_SIZE="16384",
                CPL_VSIL_CURL_CACHE_SIZE="262144",
                GDAL_HTTP_MAX_RETRY="0", GDAL_HTTP_TIMEOUT="12",
                GDAL_CACHEMAX="64")


def command(args, env=None, timeout=80):
    return subprocess.run(args, env=env, timeout=timeout,
                          check=True, capture_output=True)


def image_info(path):
    return json.loads(command(["gdalinfo","-json","-stats",str(path)],
                              timeout=30).stdout)


def alpha_minmax(info):
    values = [b for b in info.get("bands", [])
              if b.get("colorInterpretation") == "Alpha"]
    if len(values) != 1:
        raise ValueError("No unique true source coverage alpha band")
    metadata = (values[0].get("metadata") or {}).get("", {})
    mini, maxi = metadata.get("STATISTICS_MINIMUM"), metadata.get("STATISTICS_MAXIMUM")
    if mini is None or maxi is None:
        raise ValueError("No measured alpha-band statistics")
    return float(mini), float(maxi)


def render(index, candidate, out):
    ids = candidate["sourceIds"]
    if ids != sorted(candidate["pair"]) or len(ids) != 2:
        raise ValueError("Seam needs exactly two validated original sources")
    originals = [{**source(index, id), "id": id} for id in ids]
    expected = candidate["xyz"]
    if expected.get("z") != 16:
        raise ValueError("Real seam requires zoom-16 XYZ")
    z,x,y = expected["z"],expected["x"],expected["y"]
    bbox = mercator_bounds(x,y,z)
    budget = RangeBudget(PER_SEAM_MAX)
    servers, uris = [], []
    try:
        for original in originals:
            srv = ThreadingHTTPServer((HOST,0),proxy_handler(original,budget))
            srv.daemon_threads=True
            Thread(target=srv.serve_forever,daemon=True).start()
            servers.append(srv)
            uris.append(f"/vsicurl/http://{HOST}:{srv.server_port}/source.tif")
        with tempfile.TemporaryDirectory(prefix="rrgh-topo-seam-") as folder:
            temp = Path(folder)
            env = environ()
            partial = []
            for i, uri in enumerate(uris):
                p = temp / f"original-{i}-coverage.tif"
                command(["gdalwarp","-q","-overwrite","-of","GTiff",
                         "-t_srs","EPSG:3857","-te",*map(str,bbox),
                         "-ts","256","256","-dstalpha","-r","bilinear",
                         "-wm","24","-wo","NUM_THREADS=1",uri,str(p)],
                        env=env, timeout=90)
                info = image_info(p)
                minimum, maximum = alpha_minmax(info)
                if maximum <= 0:
                    raise ValueError("No source pixels for " + originals[i]["id"])
                partial.append({"id":originals[i]["id"],"alphaMin":minimum,
                                "alphaMax":maximum})
            vrt=temp/"two-originals.vrt"
            derived=temp/"mosaic.tif"
            command(["gdalbuildvrt","-q","-overwrite","-resolution","highest",
                     "-addalpha",str(vrt),*uris],env=env,timeout=80)
            command(["gdalwarp","-q","-overwrite","-of","GTiff",
                     "-t_srs","EPSG:3857","-te",*map(str,bbox),
                     "-ts","256","256","-dstalpha","-r","bilinear",
                     "-wm","32","-wo","NUM_THREADS=1",str(vrt),str(derived)],
                    env=env,timeout=100)
            info=image_info(derived)
            georef=verify_derived_grid(info,bbox)
            min_alpha,max_alpha=alpha_minmax(info)
            if min_alpha < 255 or max_alpha != 255:
                raise ValueError("True seam pixels incomplete (alpha min="
                                 +str(min_alpha)+")")
            jpg=temp/"seam.jpg"
            command(["gdal_translate","-q","-of","JPEG","-b","1","-b","2",
                     "-b","3","-co","QUALITY=90",str(derived),str(jpg)],timeout=30)
            if not jpg.is_file() or jpg.stat().st_size < 1200:
                raise ValueError("Empty or unusable seam derived image")
            output=out/f"{ids[0]}__{ids[1]}/kentucky-topo/{z}/{x}/{y}.jpg"
            if output.exists():
                raise FileExistsError("Do not overwrite previous source QA")
            output.parent.mkdir(parents=True,exist_ok=True)
            data=jpg.read_bytes()
            output.write_bytes(data)
            return {"pair":ids,"xyz":expected,"sources":originals,
                    "sourcePixelAlpha":partial,"mosaicAlphaMin":min_alpha,
                    "mosaicAlphaMax":max_alpha,"geoQA":georef,
                    "sourceBytesTransferred":budget.used,
                    "httpRangeRequests":budget.calls,
                    "jpegSha256":hashlib.sha256(data).hexdigest(),
                    "jpegBytes":len(data),"jpegPath":output.relative_to(out).as_posix(),
                    "seamAppearanceOwnerAccepted":False}
    finally:
        for srv in servers:
            srv.shutdown()
            srv.server_close()


def run(index, root, renderer=render):
    planned=plan(index)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Do not replace any previous 12-seam source QA")
    records=[]
    failures=[]
    transferred=0
    for candidate in planned["candidates"]:
        try:
            result=renderer(index,candidate,root)
            if (result["pair"]!=candidate["pair"] or
                    result["xyz"]!=candidate["xyz"] or
                    result["mosaicAlphaMin"]!=255.0 or
                    not result["geoQA"].get("pixelAndGeographicAlignmentVerified")
                    or not (0 < result["sourceBytesTransferred"]<=PER_SEAM_MAX)):
                raise ValueError("Source seam failed strict acceptance")
            records.append(result)
            transferred+=result["sourceBytesTransferred"]
            if transferred > ALL_MAX:
                raise ValueError("All-seams original-source budget exceeded")
        except Exception as exc:
            failures.append({"candidate":candidate,
                             "error":type(exc).__name__ + ": " + str(exc)[:600]})
            # Try remaining independent bounded seam samples so one inaccurate
            # index bbox cannot conceal further missing source pixels.
            continue
    if failures:
        root.mkdir(parents=True,exist_ok=True)
        (root/"BOUNDARY-FAILED-NOT-ACCEPTED.json").write_text(json.dumps({
            "status":"INCOMPLETE 12-SOURCE SEAM QA — NEVER CUSTOMER READY",
            "passed":len(records),"failed":len(failures),
            "failures":failures,
            "notAnOfflineMap":True},indent=2)+"\n")
        raise ValueError(f"{len(failures)} of 12 official seams failed actual pixel QA")
    result={"status":"12 ORIGINAL KYTOPO BOUNDARY PIXEL PILOTS, NOT REGIONAL COVERAGE",
            "candidateCount":len(records),"records":records,
            "originalBytesTransferred":transferred,
            "originalWholeTiffsDownloaded":False,
            "finalCoreDownloadBytes":None,
            "completeGorgePixelCoverage":False,
            "seamAppearanceOwnerAccepted":False,
            "notCustomerReady":True}
    root.mkdir(parents=True,exist_ok=True)
    (root/"TWELVE-SOURCE-BOUNDARY-PILOT.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--official-quads",type=Path,required=True)
    p.add_argument("--qa-root",type=Path,required=True)
    a=p.parse_args()
    r=run(json.loads(a.official_quads.read_text()),a.qa_root)
    print(json.dumps({"status":r["status"],"boundaryCount":r["candidateCount"],
                      "bytesTransferred":r["originalBytesTransferred"]},indent=2))

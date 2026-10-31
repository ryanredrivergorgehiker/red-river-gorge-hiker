#!/usr/bin/env python3
"""One-time offline-only rebind of untouched Wave022 to the ORIGINAL approved push WIF.

The earlier workflow_dispatch worker failed before Cloud authentication.
Retains that Git commit and scope as immutable historical evidence, writes a
separate, new exact-plan-bound folder and never mutates original receipts.
No cloud access. Publish uses a GitHub tree CAS, and cannot dispatch itself.
"""
import argparse,base64,json,os,re,subprocess,sys,zlib,hashlib
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

REPO="ryanredrivergorgehiker/red-river-gorge-hiker"
BRANCH="lane20/map-producer-iam-design-20261029"
EXPECTED_PARENT="8547471a41c876bacfe0a45a7d130c5dcd37d6bf"
OLD_DIR="backend/config/gorge-campaign-wave-022-20261031"
NEW_DIR="backend/config/gorge-campaign-wave-022-push-20261031"
OLD_PLAN_SHA="94a67c030795fa1f996335e5fd3aba91c30a311efefc320feee0b9b297bc766c"

def guard(ok,m):
    if not ok: raise RuntimeError("RRGH_REBIND_STOP: "+m)
def canonical(x):
    return (json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read_json(p):return json.loads(p.read_bytes())

def prepare(root):
    root=Path(root).resolve()
    guard(subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()==EXPECTED_PARENT,"Wrong input source commit")
    old=root/OLD_DIR
    new=root/NEW_DIR
    guard(old.is_dir() and not new.exists(),"Old/new config identity changed")
    plan=read_json(old/"PLAN.json")
    env=read_json(old/"ALLOWANCE.json")
    region=json.loads(zlib.decompress(base64.b64decode((old/"REGION-PLAN.json.z.b64").read_bytes())))
    guard(sha(canonical(plan))==OLD_PLAN_SHA,"Unexpected original plan digest")
    guard(plan["campaign"]["sequence"]==22 and len(plan["approvedJobIDs"])==512,"Incorrect wave and envelope")
    guard(len(plan["completedJobIDs"])==3937 and plan["campaign"]["carry"]["priorRasterTiles"]==41173,
          "Last independent settlement changed")
    guard(plan["campaign"]["carry"]["priorSunlightAssets"]==320,"Sunlight was changed")
    guard(not set(plan["approvedJobIDs"])&set(plan["completedJobIDs"]),"Completed job overlap")
    guard(plan["maxConcurrency"]==1 and plan["automaticRetryPermitted"] is False,"Retries/concurrency loosened")
    guard(plan["campaign"]["ceilingUSD"]=="25.00" and plan["campaign"]["storageTargetUSDPerMonth"]=="1.00",
          "Budget migration is a distinct later action")
    src=root/"backend/scripts"
    context=src/"fetch_gorge_private_seed.py"
    old_ctx=context.read_text()
    x="'GITHUB_EVENT_NAME':'workflow_dispatch', 'GITHUB_RUN_ATTEMPT':'1'"
    y="'GITHUB_EVENT_NAME':'push', 'GITHUB_RUN_ATTEMPT':'1'"
    a=".github/workflows/offline-map-restricted-dispatch.yml@refs/heads/lane20/offline-production-preflight-20261029"
    b=".github/workflows/offline-map-producer-access.yml@refs/heads/lane20/offline-production-preflight-20261029"
    guard(old_ctx.count(x)==1 and old_ctx.count(a)==1,"Original dispatch identity not exact")
    context.write_text(old_ctx.replace(x,y).replace(a,b))
    code=src/"gorge_campaign.py"
    old_code=code.read_text()
    before="CONFIG=SOURCE.parent/'config/gorge-campaign-wave-022-20261031'"
    after="CONFIG=SOURCE.parent/'config/gorge-campaign-wave-022-push-20261031'"
    guard(old_code.count(before)==1,"Original config pin unexpected")
    code.write_text(old_code.replace(before,after))
    for name in ("gorge_campaign.py","fetch_gorge_private_seed.py"):
        if name in region["engineHashes"]:
            region["engineHashes"][name]=sha((src/name).read_bytes())
    sys.path.insert(0,str(src))
    from run_gorge_checkpoint_slot import code_snapshot
    plan["sourceSnapshotSHA256"]=code_snapshot(src)
    plan["regionPlanSHA256"]=sha(canonical(region))
    env["cloudStorageAllowance"]["planSHA256"]=sha(canonical(plan))
    guard(env["cloudStorageAllowance"]["approvedUSD"]=="0.6456","New dollars not authorized")
    new.mkdir()
    (new/"PLAN.json").write_bytes(canonical(plan))
    (new/"ALLOWANCE.json").write_bytes(canonical(env))
    (new/"REGION-PLAN.json.z.b64").write_bytes(base64.b64encode(zlib.compress(canonical(region),9)))
    from gorge_campaign import configuration
    new_plan,evidence,new_region=configuration()
    guard(sha(canonical(new_plan))==env["cloudStorageAllowance"]["planSHA256"],"New plan readback mismatch")
    guard(new_plan["approvedJobIDs"]==plan["approvedJobIDs"],"Job list changed")
    guard(new_region["jobs"]==region["jobs"],"Raster scope changed")
    print(json.dumps({"result":"PUSH_IDENTITY_PLAN_VERIFIED","previousSHA":OLD_PLAN_SHA,
        "newPlanSHA256":env["cloudStorageAllowance"]["planSHA256"],
        "approvedJobs":len(plan["approvedJobIDs"]),
        "expectedTiles":sum(len(j["outputTiles"]) for j in region["jobs"]),
        "oldConfigPreserved":True,"cloudCalls":0},sort_keys=True))

def api(method,path,token,payload=None):
    body=canonical(payload) if payload is not None else None
    req=Request("https://api.github.com/repos/"+REPO+"/"+path,data=body,method=method,
        headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"RRGH-original-push-rebind",
        **({"Content-Type":"application/json"} if body is not None else {})})
    try:
        with urlopen(req,timeout=30) as res:
            raw=res.read(8_000_000)
    except HTTPError as e: raise RuntimeError("GitHub API "+path.split("?")[0]+" HTTP "+str(e.code)) from None
    return json.loads(raw) if raw else {}

def publish(root):
    token=os.environ.get("GH_TOKEN")
    guard(bool(token) and os.environ.get("GITHUB_REPOSITORY")==REPO,"Required restricted GitHub publication context missing")
    root=Path(root).resolve()
    guard(subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()==EXPECTED_PARENT,"Unexpected source base")
    old=read_json(root/OLD_DIR/"PLAN.json")
    new=read_json(root/NEW_DIR/"PLAN.json")
    env=read_json(root/NEW_DIR/"ALLOWANCE.json")
    guard(sha(canonical(old))==OLD_PLAN_SHA,"Prior plan modified")
    guard(new["campaign"]["sequence"]==22 and new["completedJobIDs"]==old["completedJobIDs"]
          and new["approvedJobIDs"]==old["approvedJobIDs"] and
          new["campaign"]["previousRecovery"]==old["campaign"]["previousRecovery"],"Unexpected scope migration")
    guard(sha(canonical(new))==env["cloudStorageAllowance"]["planSHA256"],"New allowance digest mismatch")
    ctx=(root/"backend/scripts/fetch_gorge_private_seed.py").read_text()
    guard("'GITHUB_EVENT_NAME':'push'" in ctx and
          "offline-map-producer-access.yml@refs/heads/lane20/offline-production-preflight-20261029" in ctx,
          "Original trusted workflow not restored")
    engine=(root/"backend/scripts/gorge_campaign.py").read_text()
    guard("CONFIG=SOURCE.parent/'config/gorge-campaign-wave-022-push-20261031'" in engine,"Wrong engine config")
    latest=api("GET","git/ref/heads/"+BRANCH,token)["object"]["sha"]
    guard(latest==EXPECTED_PARENT,"Source branch lease changed")
    paths=["backend/scripts/gorge_campaign.py","backend/scripts/fetch_gorge_private_seed.py",
           NEW_DIR+"/PLAN.json",NEW_DIR+"/ALLOWANCE.json",NEW_DIR+"/REGION-PLAN.json.z.b64"]
    tree=[{"path":p,"mode":"100644","type":"blob","content":(root/p).read_text()} for p in paths]
    guard(all(len(e["content"])<500000 for e in tree),"Unexpected file size")
    commit_obj=api("GET","git/commits/"+EXPECTED_PARENT,token)
    t=api("POST","git/trees",token,{"base_tree":commit_obj["tree"]["sha"],"tree":tree})
    newcommit=api("POST","git/commits",token,{"message":"Lane20: prepare original-identity Wave022 guarded production source [skip ci]",
              "tree":t["sha"],"parents":[EXPECTED_PARENT]})
    api("PATCH","git/refs/heads/"+BRANCH,token,{"sha":newcommit["sha"],"force":False})
    guard(api("GET","git/ref/heads/"+BRANCH,token)["object"]["sha"]==newcommit["sha"],"Source CAS readback failed")
    print(json.dumps({"status":"REBOUND_WAVE022_SOURCE_PUBLISHED_NO_CLOUD",
      "sourceSHA":newcommit["sha"],"planSHA256":sha(canonical(new)),
      "jobs":512,"triggered":False},sort_keys=True))

if __name__=="__main__":
    try:
        ap=argparse.ArgumentParser()
        ap.add_argument("source_checkout")
        ap.add_argument("--publish",action="store_true")
        args=ap.parse_args()
        if not args.publish:prepare(args.source_checkout)
        else:publish(args.source_checkout)
    except Exception as e:
        print("RRGH_WAVE22_REBIND_FAILED: "+str(e),file=sys.stderr);sys.exit(1)

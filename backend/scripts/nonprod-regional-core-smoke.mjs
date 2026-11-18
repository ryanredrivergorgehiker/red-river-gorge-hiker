// Bounded live proof of genuine nonproduction Core delivery through existing
// UID/Base, signed offline lease, and generation-pinned capability downloader.
// Three complete indexes + one 16 KiB archive sample per group; NO bulk download.
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
const req = createRequire(new URL("../functions/package.json", import.meta.url));
const { applicationDefault, initializeApp } = req("firebase-admin/app");
const { getAuth } = req("firebase-admin/auth");
const { getFirestore } = req("firebase-admin/firestore");
const { verifyOfflineLeaseToken } = await import("../functions/src/offlineLease.js");
const uid="github-ci-regional-core-smoke";
const api=process.env.RRGH_FUNCTION_URL;
const apiKey=process.env.FIREBASE_API_KEY;
const serviceAccountId=process.env.RRGH_DEPLOY_SERVICE_ACCOUNT;
const groups=["gorge-core","gorge-aerial-leaf-on","gorge-aerial-leaf-off"];
const requireOk=(x,m)=>{if(!x) throw Error(m);};
requireOk(api?.startsWith("https://") && apiKey && serviceAccountId,
  "Missing governed nonproduction smoke configuration");
const app=initializeApp({credential:applicationDefault(),
  projectId:"rrgh-nonproduction",serviceAccountId});
const db=getFirestore(app),auth=getAuth(app);
async function getJson(r){const b=await r.json();requireOk(b&&typeof b==="object","Malformed JSON");return b;}
async function call(operation,token,extra={}){
  const r=await fetch(api,{method:"POST",
    headers:{"content-type":"application/json",...(token?{authorization:"Bearer "+token}:{})},
    body:JSON.stringify({data:{operation,...extra}})});
  return {http:r.status,body:await getJson(r)};
}
async function clean(){
  const acc=db.collection("accounts").doc(uid);
  for(const sub of ["entitlements","purchaseEvidence"]){
    const items=await acc.collection(sub).get();
    if(!items.empty){const batch=db.batch();items.docs.forEach(x=>batch.delete(x.ref));await batch.commit();}
  }
  const caps=await db.collection("packageCapabilities").where("uid","==",uid).get();
  if(!caps.empty){const batch=db.batch();caps.docs.forEach(x=>batch.delete(x.ref));await batch.commit();}
  await db.collection("accountDeletionRequests").doc(uid).delete().catch(()=>{});
  await acc.delete().catch(()=>{});
  try{await auth.deleteUser(uid);}catch(e){if(e?.code!=="auth/user-not-found")throw e;}
}
async function probe(token,id,full){
  const {http,body}=await call("authorizeProtectedPackage",token,{packageId:id});
  const result=body.result,p=result?.package,d=result?.delivery;
  requireOk(http===200&&result?.authorized===true&&d?.ready===true,
    "Protected regional authorization failed");
  requireOk(p?.packageId===id&&p?.packageType==="offline_base"&&
    p?.requiredEntitlement==="base"&&typeof p.version==="string"&&
    Number.isSafeInteger(p.byteCount)&&p.byteCount>0&&
    /^[0-9a-f]{64}$/.test(p.sha256)&&d.method==="capability_https"&&
    d.httpMethod==="GET"&&d.authorizationScheme==="Bearer"&&
    typeof d.authorizationToken==="string"&&d.authorizationToken.length>=32&&
    d.url?.startsWith("https://"),"Protected regional contract malformed");
  const count=full?p.byteCount:Math.min(16384,p.byteCount);
  requireOk(!full||count<=1048576,"Index over strict 1 MiB test cap");
  const end=count-1;
  const dl=await fetch(d.url,{headers:{
    authorization:"Bearer "+d.authorizationToken,range:"bytes=0-"+end}});
  requireOk(dl.status===206 &&
    dl.headers.get("content-range")==="bytes 0-"+end+"/"+p.byteCount &&
    dl.headers.get("x-rrgh-package-id")===id &&
    dl.headers.get("x-rrgh-package-version")===p.version,
    "Protected generation-pinned range response invalid");
  const bytes=Buffer.from(await dl.arrayBuffer());
  requireOk(bytes.length===count,"Partial byte count mismatch");
  if(full)requireOk(createHash("sha256").update(bytes).digest("hex")===p.sha256,
    "Original regional index end-to-end SHA mismatch");
}
let passed=false;
try{
  await clean();
  const unauth=await call("getAccountState",null);
  requireOk(unauth.http===401,"Unauthenticated callable not denied");
  const custom=await auth.createCustomToken(uid,{purpose:"rrgh-regional-smoke"});
  const signedResponse=await fetch(
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key="+encodeURIComponent(apiKey),
    {method:"POST",headers:{"content-type":"application/json"},
      body:JSON.stringify({token:custom,returnSecureToken:true})});
  const signed=await getJson(signedResponse);
  requireOk(signedResponse.ok&&signed.idToken,"Firebase test session failed");
  const denied=await call("authorizeProtectedPackage",signed.idToken,{packageId:"gorge-core"});
  requireOk(denied.body.result?.authorized!==true &&
    denied.body.result?.delivery==null,"Region accessible without Base");
  const trial=await call("startBaseTrial",signed.idToken);
  requireOk(trial.http===200&&trial.body.result?.account?.access?.base===true,
    "Base trial entitlement not effective");
  const lease=await call("issueOfflineAccessLease",signed.idToken);
  const response=lease.body.result;
  requireOk(lease.http===200&&response?.issued===true,"Signed lease not issued");
  const validated=verifyOfflineLeaseToken({
    signedToken:response.lease.signedToken,keyId:response.lease.keyId,
    verificationKeys:response.verificationKeys,expectedUid:uid});
  requireOk(validated.valid===true&&validated.claims?.trial===true&&
    validated.claims?.grants?.includes("base"),"UID-bound Base lease invalid");
  const entries=(await db.collection("packageCatalog").get()).docs.filter(d=>
    groups.some(g=>d.id===g||d.id.startsWith(g+"-")));
  requireOk(entries.length===125,"125 active region records not found");
  requireOk(entries.every(d=>{
    const p=d.data();return p.active===true&&p.contentReady===true&&
      p.deliveryState==="ready"&&p.lifecycle==="active"&&
      p.requiredEntitlement==="base"&&
      p.storageBucket==="rrgh-nonproduction-protected-packages"&&
      typeof p.objectGeneration==="string"&&/^[1-9][0-9]*$/.test(p.objectGeneration);
  }),"Regional identity/state drift");
  for(const group of groups){
    const index=entries.find(d=>d.id===group);
    const part=entries.find(d=>d.id.startsWith(group+"-"));
    requireOk(index&&part,"One verified region family is incomplete");
    await probe(signed.idToken,index.id,true);
    await probe(signed.idToken,part.id,false);
  }
  console.log("AUTHENTICATED_NONPROD_REGIONAL_DELIVERY_PASS");
  console.log("THREE_COMPLETE_INDEX_SHA256=VERIFIED");
  console.log("THREE_ORIGINAL_ARCHIVE_PART_BOUNDED_RANGES=VERIFIED");
  console.log("ALL_125_CATALOG_RECORDS_ACTIVE=VERIFIED");
  console.log("UID_BASE_TRIAL_OFFLINE_LEASE=VERIFIED");
  console.log("CUSTOMER_RELEASE=FALSE; FULL_ARCHIVE_DOWNLOAD=NOT_RUN; IPHONE_ACCEPTANCE=LANE21");
  passed=true;
} finally{
  await clean();
  console.log("TEMPORARY_NONPROD_TEST_ACCOUNT_CLEANED="+(passed?"TRUE":"AFTER_FAILED_TEST"));
}

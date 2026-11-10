import {createHash,generateKeyPairSync,randomBytes,privateDecrypt,constants,createDecipheriv} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';

export const REPO='ryanredrivergorgehiker/red-river-gorge-hiker', BRANCH='backend/phase-3-nonprod';
export const BUCKET='rrgh-nonproduction-protected-packages';
export const PACK_SHA='fcdd9ba6ac9f8b61f032b28ee28aac7bcb48bf045932fcefc9f1130b7a9bbaed';
export const INDEX_SHA='278272b57c24bd01ecd9efe7503bcfb77455173d84ffb209bee2f8828aa0a394';
export const ARCHIVE_SHA='38f6bcb6337f8f087851d1ebbaafa5dd810a346b04c84f6fdffe892240c07290';
export function requireValue(v,m){if(!v)throw new Error(m);}
export function sha(v){return createHash('sha256').update(v).digest('hex');}
export function canonical(v){if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';return JSON.stringify(v);}
export function digest(v){return sha(Buffer.from(canonical(v)+'\n'));}
export function codeDigest(){return digest(Object.fromEntries(['.github/automation/r4/restore.mjs','.github/automation/r4/restore.test.mjs','.github/workflows/rrgh-r4-restoration.yml'].map(p=>[p,sha(readFileSync(p))])));}

export function validatePayload(raw){
  requireValue(raw.length===4913929,'Exact original payload length required');
  const index=raw.subarray(0,68063),pack=raw.subarray(68063);
  requireValue(sha(index)===INDEX_SHA&&sha(pack)===PACK_SHA,'Original archive payload hashes changed');
  const m=JSON.parse(index);
  requireValue(m.format==='rrgh-preserved-r4-restoration-v1'&&m.archiveSHA256===ARCHIVE_SHA&&m.jobCount===12&&m.rasterTiles===172&&m.bytes===4845866,'Original restoration inventory changed');
  const seen=new Set();let count=0,cursor=0;
  for(const j of m.jobs){
    requireValue(/^(leaf-on|leaf-off|usgs-topo)-16-(17544|17545)-(25322|25323)$/.test(j.job)&&!seen.has(j.job)&&j.originalReceipt.job===j.job&&j.originalReceipt.validated===true,'Original job identity changed');seen.add(j.job);
    requireValue(j.members.length===j.originalReceipt.outputs.length,'Original output count changed');
    for(let n=0;n<j.members.length;n++){
      const e=j.members[n],o=j.originalReceipt.outputs[n];
      requireValue(e.offset===cursor&&Number.isSafeInteger(e.bytes)&&e.bytes>0&&e.bytes<=524288&&['path','bytes','sha256'].every(k=>e[k]===o[k])&&sha(pack.subarray(cursor,cursor+e.bytes))===e.sha256,'Preserved output bytes changed');
      cursor+=e.bytes;count++;
    }
  }
  requireValue(seen.size===12&&count===172&&cursor===pack.length,'Preserved output inventory incomplete');return {index,pack};
}

export function decryptEnvelope(manifest,chunks,privateKey,session){
  requireValue(manifest.format==='rrgh-encrypted-restoration-v1'&&manifest.runID===session.runID&&manifest.nonce===session.nonce&&manifest.publicKeySHA256===session.publicKeySHA256,'Envelope belongs to another runner');
  requireValue(chunks.length===manifest.chunks.length&&chunks.length>0&&chunks.length<=80,'Ciphertext chunk bound');
  chunks.forEach((b,i)=>requireValue(b.length===manifest.chunks[i].bytes&&b.length<=65536&&sha(b)===manifest.chunks[i].sha256,'Ciphertext chunk changed'));
  const ciphertext=Buffer.concat(chunks);requireValue(ciphertext.length===4913929&&sha(ciphertext)===manifest.ciphertextSHA256,'Ciphertext extent changed');
  const key=privateDecrypt({key:privateKey,oaepHash:'sha256',padding:constants.RSA_PKCS1_OAEP_PADDING},Buffer.from(manifest.encryptedKey,'base64'));
  requireValue(key.length===32,'Invalid key size');
  const decipher=createDecipheriv('aes-256-gcm',key,Buffer.from(manifest.iv,'base64'));
  decipher.setAAD(Buffer.from(session.nonce));decipher.setAuthTag(Buffer.from(manifest.tag,'base64'));
  const plaintext=Buffer.concat([decipher.update(ciphertext),decipher.final()]);key.fill(0);return plaintext;
}

async function main(){
  const env=process.env,runID=env.GITHUB_RUN_ID;
  requireValue(env.GITHUB_REPOSITORY===REPO&&env.GITHUB_REF==='refs/heads/'+BRANCH&&env.GITHUB_ACTOR==='ryanredrivergorgehiker'&&env.GITHUB_EVENT_NAME==='push'&&env.GITHUB_RUN_ATTEMPT==='1'&&/^\d+$/.test(runID),'Exact authorized runner required');
  const request=JSON.parse(readFileSync('operations/rrgh-r4-restoration-request.json'));const {requestSHA256,...body}=request;
  requireValue(digest(body)===requestSHA256&&request.codeSHA256===codeDigest()&&request.authorizedBy==='ryanredrivergorgehiker'&&request.format==='rrgh-r4-restoration-request-v1'&&request.packSHA256===PACK_SHA&&request.indexSHA256===INDEX_SHA&&request.reservedUSD==='0.05','Exact reviewed restoration request required');
  let githubRequests=0;
  async function github(path,options={}){
    requireValue(++githubRequests<=180,'GitHub transfer request bound');
    const response=await fetch('https://api.github.com/repos/'+REPO+'/'+path,{...options,headers:{Authorization:'Bearer '+env.GH_TOKEN,Accept:'application/vnd.github+json','Content-Type':'application/json'},signal:AbortSignal.timeout(30000)});
    if(response.status===404)return null;requireValue(response.ok,'GitHub transfer HTTP '+response.status);
    const raw=await response.text();requireValue(raw.length<=200000,'GitHub transfer response bound');return JSON.parse(raw);
  }
  const {publicKey,privateKey}=generateKeyPairSync('rsa',{modulusLength:3072,publicKeyEncoding:{type:'spki',format:'pem'},privateKeyEncoding:{type:'pkcs8',format:'pem'}});
  const session={format:'rrgh-ephemeral-restoration-session-v1',runID,headSHA:env.GITHUB_SHA,requestSHA256,nonce:randomBytes(32).toString('hex'),publicKey,publicKeySHA256:sha(publicKey)};
  const prefix='operations/rrgh-r4-transit/'+runID+'/';
  await github('contents/'+prefix+'session.json',{method:'PUT',body:JSON.stringify({message:'Publish ephemeral public key for exact preserved R4 restoration',branch:BRANCH,content:Buffer.from(JSON.stringify(session)+'\n').toString('base64')})});
  console.log(JSON.stringify({phase:'waiting-for-encrypted-preserved-tiles',runID,privateKeyExported:false}));
  let manifest=null;
  for(let i=0;i<72;i++){
    const file=await github('contents/'+prefix+'response.json?ref='+encodeURIComponent(BRANCH));
    if(file){requireValue(file.encoding==='base64'&&file.size<=32768,'Envelope manifest bound');manifest=JSON.parse(Buffer.from(file.content,'base64'));break;}
    await new Promise(resolve=>setTimeout(resolve,10000));
  }
  requireValue(manifest,'Encrypted handoff did not arrive');
  requireValue(Array.isArray(manifest.chunks)&&manifest.chunks.length<=80,'Encrypted chunk count');
  const chunks=[];
  for(const c of manifest.chunks){requireValue(/^[0-9a-f]{40}$/.test(c.blobSHA),'Exact encrypted Git blob required');const blob=await github('git/blobs/'+c.blobSHA);requireValue(blob&&blob.encoding==='base64'&&blob.size<=65536,'Encrypted blob bound');chunks.push(Buffer.from(blob.content,'base64'));}
  const raw=decryptEnvelope(manifest,chunks,privateKey,session),{pack,index}=validatePayload(raw);
  const token=execFileSync('gcloud',['auth','print-access-token','--quiet'],{encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();
  const objectPrefix='engineering/map-production/restorations/r4/'+PACK_SHA+'/';let cloudRequests=0,readBytes=0;
  async function cloud(url,options={}){
    requireValue(++cloudRequests<=12,'Cloud request bound');
    const r=await fetch(url,{...options,headers:{...options.headers,Authorization:'Bearer '+token,'Accept-Encoding':'identity'},signal:AbortSignal.timeout(90000)});requireValue(r.ok,'Restoration Cloud HTTP '+r.status);
    const b=Buffer.from(await r.arrayBuffer());readBytes+=b.length;requireValue(readBytes<=8*2**20,'Cloud readback bound');return b;
  }
  async function put(name,bytes,expected){
    const result=JSON.parse(await cloud('https://storage.googleapis.com/upload/storage/v1/b/'+BUCKET+'/o?uploadType=media&ifGenerationMatch=0&name='+encodeURIComponent(objectPrefix+name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:bytes}));
    requireValue(result.bucket===BUCKET&&result.name===objectPrefix+name&&Number(result.size)===bytes.length&&/^\d+$/.test(result.generation),'Created object identity changed');
    const recovered=await cloud('https://storage.googleapis.com/storage/v1/b/'+BUCKET+'/o/'+encodeURIComponent(result.name)+'?alt=media&generation='+result.generation+'&ifGenerationMatch='+result.generation);
    requireValue(recovered.length===bytes.length&&sha(recovered)===expected,'Restored object readback differs');return {key:result.name,generation:result.generation,bytes:bytes.length,sha256:expected};
  }
  const claim=Buffer.from(canonical({format:'rrgh-r4-restoration-claim-v1',requestSHA256,runID,headSHA:env.GITHUB_SHA,reservedUSD:'0.05',archiveSHA256:ARCHIVE_SHA})+'\n');
  await put('claim.json',claim,sha(claim));
  const packRef=await put('preserved-tiles.pack',pack,PACK_SHA),indexRef=await put('preserved-jobs.json',index,INDEX_SHA);
  console.log(JSON.stringify({phase:'preserved-r4-restoration',status:'verified',runID,requestSHA256,archiveSHA256:ARCHIVE_SHA,packRef,indexRef,jobs:12,rasterTiles:172,sourceRequests:0,rasterJobsExecuted:0,cloudRequests,readBytes,originalBytesPreserved:true}));raw.fill(0);
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)main().catch(()=>{console.error('Preserved R4 restoration failed; no replay or overwrite permitted.');process.exitCode=1;});

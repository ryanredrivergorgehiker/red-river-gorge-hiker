import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,randomBytes,createCipheriv,publicEncrypt,constants} from 'node:crypto';
import {sha,decryptEnvelope,validatePayload} from './restore.mjs';
const pair=generateKeyPairSync('rsa',{modulusLength:3072});
function fixture(){
  const raw=Buffer.alloc(4913929,79),key=randomBytes(32),iv=randomBytes(12),session={runID:'123',nonce:'a'.repeat(64),publicKeySHA256:'b'.repeat(64)};
  const cipher=createCipheriv('aes-256-gcm',key,iv);cipher.setAAD(Buffer.from(session.nonce));
  const ciphertext=Buffer.concat([cipher.update(raw),cipher.final()]),chunks=[];
  for(let i=0;i<ciphertext.length;i+=65536)chunks.push(ciphertext.subarray(i,i+65536));
  const manifest={format:'rrgh-encrypted-restoration-v1',...session,encryptedKey:publicEncrypt({key:pair.publicKey,oaepHash:'sha256',padding:constants.RSA_PKCS1_OAEP_PADDING},key).toString('base64'),iv:iv.toString('base64'),tag:cipher.getAuthTag().toString('base64'),ciphertextSHA256:sha(ciphertext),chunks:chunks.map(b=>({bytes:b.length,sha256:sha(b)}))};
  return {raw,manifest,chunks,session};
}
test('full bounded payload decrypts only for the originating runner key',()=>{const f=fixture();assert.deepEqual(decryptEnvelope(f.manifest,f.chunks,pair.privateKey,f.session),f.raw);});
test('another runner or nonce is rejected before decrypting',()=>{const f=fixture();for(const k of ['runID','nonce','publicKeySHA256'])assert.throws(()=>decryptEnvelope({...f.manifest,[k]:'wrong'},f.chunks,pair.privateKey,f.session));});
test('modified ciphertext cannot pass its original hash',()=>{const f=fixture();const changed=f.chunks.map(b=>Buffer.from(b));changed[0][0]^=1;assert.throws(()=>decryptEnvelope(f.manifest,changed,pair.privateKey,f.session),/chunk changed/);});
test('changed authentication tag cannot decrypt',()=>{const f=fixture();assert.throws(()=>decryptEnvelope({...f.manifest,tag:Buffer.alloc(16).toString('base64')},f.chunks,pair.privateKey,f.session));});
test('arbitrary bytes of the correct length cannot become accepted original tiles',()=>{assert.throws(()=>validatePayload(Buffer.alloc(4913929)),/hashes changed/);assert.throws(()=>validatePayload(Buffer.alloc(1)),/length required/);});

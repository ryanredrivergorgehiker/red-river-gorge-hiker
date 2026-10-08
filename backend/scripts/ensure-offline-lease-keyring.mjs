#!/usr/bin/env node
import fs from "node:fs";
import {
  createHash,
  generateKeyPairSync,
} from "node:crypto";

const path = process.argv[2];
if (!path) {
  throw new Error("Usage: ensure-offline-lease-keyring.mjs <keyring-json-path>");
}

function validate(keyring) {
  if (
    !keyring ||
    keyring.version !== 1 ||
    typeof keyring.activeKeyId !== "string" ||
    !Array.isArray(keyring.keys) ||
    keyring.keys.length < 1
  ) {
    throw new Error("Invalid offline lease keyring.");
  }

  const seen = new Set();
  for (const key of keyring.keys) {
    if (
      !key ||
      typeof key.keyId !== "string" ||
      seen.has(key.keyId) ||
      key.algorithm !== "RS256" ||
      typeof key.privateKeyPkcs8Base64 !== "string" ||
      key.privateKeyPkcs8Base64.length < 100 ||
      typeof key.publicKeySpkiBase64 !== "string" ||
      key.publicKeySpkiBase64.length < 100
    ) {
      throw new Error("Invalid offline lease signing key.");
    }
    seen.add(key.keyId);
  }
  if (!seen.has(keyring.activeKeyId)) {
    throw new Error("Active offline lease signing key is absent.");
  }
}

if (fs.existsSync(path)) {
  validate(JSON.parse(fs.readFileSync(path, "utf8")));
  console.log("Offline lease private keyring validation: PASS");
  process.exit(0);
}

const { publicKey, privateKey } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
});
const publicDer = publicKey.export({
  format: "der",
  type: "spki",
});
const privateDer = privateKey.export({
  format: "der",
  type: "pkcs8",
});
const keyId =
  "rrgh-offline-lease-v1-" +
  createHash("sha256")
    .update(publicDer)
    .digest("hex")
    .slice(0, 24);

const keyring = {
  version: 1,
  activeKeyId: keyId,
  keys: [
    {
      keyId,
      algorithm: "RS256",
      createdAt: new Date().toISOString(),
      publicKeySpkiBase64: Buffer.from(publicDer).toString("base64"),
      privateKeyPkcs8Base64: Buffer.from(privateDer).toString("base64"),
    },
  ],
};

validate(keyring);
fs.writeFileSync(path, JSON.stringify(keyring) + "\n", {
  encoding: "utf8",
  mode: 0o600,
});
console.log("Offline lease private keyring created: PASS");

import fs from "node:fs";
import { applicationDefault, initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";

const projectId = process.env.GCLOUD_PROJECT || "rrgh-nonproduction";
const catalogPath = new URL("../package-catalog.nonprod.json", import.meta.url);
const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf8"));

initializeApp({
  credential: applicationDefault(),
  projectId,
});

const db = getFirestore();

for (const item of catalog.packages) {
  const payload = {
    ...item,
    updatedAt: Timestamp.now(),
    policyVersion: 1,
  };
  await db.collection("packageCatalog").doc(item.packageId).set(payload, {
    merge: false,
  });
  console.log(
    "Synced package catalog metadata:",
    item.packageId,
    item.version,
    item.deliveryReady ? "ready-declared" : "not-ready",
  );
}

console.log("Package catalog sync: PASS");

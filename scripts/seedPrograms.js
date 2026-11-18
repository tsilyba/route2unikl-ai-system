const admin = require('firebase-admin');
const fs = require('fs');
const path = require('path');

const serviceAccountPath = path.join(__dirname, '..', 'backend', 'serviceAccountKey.json');
const serviceAccount = JSON.parse(fs.readFileSync(serviceAccountPath, 'utf8'));

if (!admin.apps.length) {
  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
  });
}

const db = admin.firestore();

const jsonPath = path.join(__dirname, '..', 'frontend', 'src', 'assets', 'unikl_foundation_testplan.json');
const foundationData = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

async function seed() {
  console.log(`Starting Admin Firestore sync of ${foundationData.length} programmes...`);
  try {
    const validIds = new Set(foundationData.map((p) => p.program_id));

    // 1. Delete any old random-ID documents from previous CSV uploads
    const existingSnap = await db.collection('programs').get();
    let removedCount = 0;
    for (const existingDoc of existingSnap.docs) {
      if (!validIds.has(existingDoc.id)) {
        await db.collection('programs').doc(existingDoc.id).delete();
        removedCount++;
        console.log(`🧹 Deleted old duplicate/CSV record (ID: ${existingDoc.id})`);
      }
    }

    // 2. Upsert the 35 official programmes with clean program_id
    for (const prog of foundationData) {
      const docRef = db.collection('programs').doc(prog.program_id);
      await docRef.set(prog, { merge: true });
      console.log(`✓ Uploaded: ${prog.title} (ID: ${prog.program_id})`);
    }
    console.log(`🎉 Seeding complete! Removed ${removedCount} old CSV record(s). Total in Firestore: ${foundationData.length}`);
  } catch (err) {
    console.error('❌ Seeding failed:', err);
  }
}

seed();


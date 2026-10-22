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
  console.log(`Starting Admin Firestore upload of ${foundationData.length} programmes...`);
  try {
    for (const prog of foundationData) {
      const docRef = db.collection('programs').doc(prog.program_id);
      await docRef.set(prog, { merge: true });
      console.log(`✓ Uploaded: ${prog.title} (ID: ${prog.program_id})`);
    }
    console.log('🎉 Seeding successfully completed via Admin SDK!');
  } catch (err) {
    console.error('❌ Seeding failed:', err);
  }
}

seed();


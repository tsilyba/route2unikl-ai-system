import { db } from '../firebase';
import { collection, doc, getDocs, setDoc, deleteDoc } from 'firebase/firestore';
import foundationData from './unikl_foundation_testplan.json';

export const seedFoundationPrograms = async () => {
  console.log(`Starting Firestore sync of ${foundationData.length} Foundation & Diploma programmes...`);

  try {
    const validIds = new Set(foundationData.map((p) => p.program_id));

    // 1. Remove any old random-ID documents from previous CSV uploads to prevent duplicates
    const existingSnap = await getDocs(collection(db, "programs"));
    let removedCount = 0;
    for (const existingDoc of existingSnap.docs) {
      if (!validIds.has(existingDoc.id)) {
        await deleteDoc(doc(db, "programs", existingDoc.id));
        removedCount++;
        console.log(`🧹 Deleted old duplicate/CSV record (ID: ${existingDoc.id})`);
      }
    }

    // 2. Upsert the 35 official programmes using their clean program_id
    for (const prog of foundationData) {
      const docRef = doc(db, "programs", prog.program_id);
      await setDoc(docRef, prog, { merge: true });
      console.log(`✓ Uploaded: ${prog.title} (ID: ${prog.program_id})`);
    }

    alert(
      `Firestore synced! 🎉\n` +
      `• Cleaned up ${removedCount} old CSV record(s)\n` +
      `• Total programmes in Firestore: ${foundationData.length}`
    );
    return { success: true, count: foundationData.length, removedCount };
  } catch (error) {
    console.error("Error uploading programmes:", error);
    alert("Seeding failed. Check console and Firestore rules.");
    return { success: false, error };
  }
};
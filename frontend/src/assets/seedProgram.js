import { db } from '../firebase';
import { doc, setDoc } from 'firebase/firestore';
import foundationData from './unikl_foundation_testplan.json';

export const seedFoundationPrograms = async () => {
  console.log(`Starting Firestore upload of ${foundationData.length} Foundation programmes...`);

  try {
    for (const prog of foundationData) {
      // Use the clean program_id as the document ID
      const docRef = doc(db, "programs", prog.program_id);
      await setDoc(docRef, prog, { merge: true });
      console.log(`✓ Uploaded: ${prog.title} (ID: ${prog.program_id})`);
    }
    alert(`All ${foundationData.length} Foundation programmes successfully updated in Firestore! 🎉`);
    return { success: true, count: foundationData.length };
  } catch (error) {
    console.error("Error uploading programmes:", error);
    alert("Seeding failed. Check console and Firestore rules.");
    return { success: false, error };
  }
};
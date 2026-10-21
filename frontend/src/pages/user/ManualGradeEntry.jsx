import React, { useState, useEffect } from 'react';
import { db, auth } from '../../firebase';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';
import { onAuthStateChanged } from 'firebase/auth';

const MIN_REQUIREMENTS = [
  { subject: 'BAHASA MELAYU', grade: '' },
  { subject: 'BAHASA INGGERIS', grade: '' },
  { subject: 'MATEMATIK', grade: '' },
  { subject: 'SEJARAH', grade: '' }
];

const ManualGradeEntry = () => {
  const [grades, setGrades] = useState([...MIN_REQUIREMENTS]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // 1. STRICT ROLE VERIFICATION
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (!user) {
        navigate('/login');
        return;
      }

      try {
        const userDoc = await getDoc(doc(db, "users", user.uid));
        if (userDoc.exists()) {
          const userData = userDoc.data();
          
          if (userData.role !== 'form_4_5') {
            alert("Access Denied: This manual entry page is strictly for Form 4 and Form 5 students.");
            navigate('/dashboard'); 
          } else {
            setLoading(false); 
          }
        }
      } catch (error) {
        console.error("Role verification failed:", error);
      }
    });

    return () => unsubscribe();
  }, [navigate]);

  const handleEditChange = (index, field, value) => {
    const newGrades = [...grades];
    // Automatically convert grades and subjects to uppercase for clean database entry
    newGrades[index][field] = value.toUpperCase();
    setGrades(newGrades);
  };

  const addEmptyRow = () => {
    setGrades([...grades, { subject: '', grade: '' }]);
  };

  // 2. UNIFIED DATABASE SAVING LOGIC
  const handleSaveAndProceed = async () => {
    const mandatoryMissing = grades.slice(0, 4).some(r => r.grade.trim() === '');
    if (mandatoryMissing) {
      alert("Please ensure BM, BI, Math, and Sejarah have grades.");
      return;
    }

    const cleanedResults = grades.filter(r => r.subject.trim() !== '' && r.grade.trim() !== '');

    try {
      const user = auth.currentUser;
      if (user) {
        // Saving to the unified 'results' collection
        const resultDocRef = doc(db, "results", user.uid);
        
        await setDoc(resultDocRef, {
          userId: user.uid,
          email: user.email,
          results: cleanedResults,
          updatedAt: new Date(),
          status: "manual_entry",
          recordType: "PREDICTED_GRADES", 
          verificationMethod: "MANUAL_ENTRY" 
        });

        // Update step tracking
        await updateDoc(doc(db, "users", user.uid), { hasUploadedResults: true });

        alert(" Grades securely saved! Proceeding to the AI Assessment.");
        navigate('/ai-assessment'); // Routing straight to the cloud AI page
      }
    } catch (error) {
      console.error("Error saving manual grades:", error);
      alert("Failed to save to Firestore. Check your database rules.");
    }
  };

  // Prevent UI flashing while checking the user's role
  if (loading) {
    return <div className="min-h-screen flex items-center justify-center font-bold text-gray-500">Verifying Security Credentials...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-3xl mx-auto bg-white rounded-3xl shadow-lg p-8">

        <div className="flex justify-between items-center mb-12 border-b pb-8">
          {['Upload Results', 'AI Assessment', 'Recommendation', 'Preparation Plan'].map((step, idx) => (
            <div key={idx} className="flex flex-col items-center flex-1 relative">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold mb-2 z-10
                ${idx === 0 ? 'bg-blue-600 text-white shadow-md' : 'bg-gray-100 text-gray-400'}`}>
                {idx === 0 ? '✓' : idx + 1}
              </div>
              <span className={`text-xs font-bold ${idx === 0 ? 'text-blue-600' : 'text-gray-400'}`}>{step}</span>
              {idx < 3 && <div className="absolute top-5 left-1/2 w-full h-[2px] bg-gray-100 -z-0"></div>}
            </div>
          ))}
        </div>
        
        <div className="mb-8 text-center">
          <span className="bg-blue-100 text-blue-700 px-4 py-1 rounded-full text-xs font-bold tracking-wide uppercase">
            Form 4 / 5 Academic Profile
          </span>
          <h2 className="text-2xl font-bold text-gray-800 mt-4">Enter Your Current Grades</h2>
          <p className="text-gray-500 text-sm mt-2">Enter your latest exam results here.</p>
        </div>

        <div className="space-y-4">
          <div className="flex gap-3 px-2 text-xs font-bold text-gray-400 uppercase tracking-wider">
            <div className="flex-1">Mata Pelajaran / Subject</div>
            <div className="w-20 text-center">Gred</div>
          </div>

          {grades.map((item, idx) => (
            <div key={idx} className="flex gap-3 p-3 bg-gray-50 rounded-xl border">
              <input 
                type="text" 
                value={item.subject} 
                placeholder="Mata Pelajaran" 
                readOnly={idx < 4} 
                onChange={(e) => handleEditChange(idx, 'subject', e.target.value)}
                className={`flex-1 p-3 border rounded-lg font-bold text-sm outline-none focus:ring-2 focus:ring-blue-400
                  ${idx < 4 ? 'bg-gray-200 text-gray-600' : 'bg-white'}`}
              />
              <input 
                type="text" 
                value={item.grade} 
                placeholder="A, B+, C..." 
                maxLength={2}
                onChange={(e) => handleEditChange(idx, 'grade', e.target.value)}
                className="w-20 p-3 border bg-white rounded-lg text-center font-black text-blue-600 outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
          ))}
        </div>

        <button onClick={addEmptyRow} className="mt-4 text-sm font-bold text-blue-600 hover:text-blue-800 transition">
          + Add Elective Subject
        </button>

        <div className="mt-10 pt-6 border-t">
          <button 
            onClick={handleSaveAndProceed} 
            className="w-full py-4 bg-blue-600 text-white font-bold rounded-xl shadow-lg hover:bg-blue-700 transition"
          >
            Save Grades
          </button>
        </div>

      </div>
    </div>
  );
};

export default ManualGradeEntry;
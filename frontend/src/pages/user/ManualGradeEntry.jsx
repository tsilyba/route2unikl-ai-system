import { useState, useEffect } from 'react';
import { db, auth } from '../../firebase';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';
import { onAuthStateChanged } from 'firebase/auth';
import Stepper from '../../components/Stepper';
import { createBaseRows, MAX_SUBJECTS, validateGradeRows } from '../../utils/gradeEntry';

// Full-page message used instead of an endless loading screen.
const StatusCard = ({ title, text, buttonLabel, onAction }) => (
  <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
    <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100 text-center" role="alert">
      <h2 className="text-2xl font-bold mb-3 text-blue-600">{title}</h2>
      <p className="text-gray-600 text-sm mb-6">{text}</p>
      <button
        type="button"
        onClick={onAction}
        className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300 cursor-pointer"
      >
        {buttonLabel}
      </button>
    </div>
  </div>
);

const ManualGradeEntry = () => {
  const [grades, setGrades] = useState(createBaseRows);
  // 'loading' | 'ready' | 'missing-profile' | 'error'
  const [pageState, setPageState] = useState('loading');
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
        if (!userDoc.exists()) {
          setPageState('missing-profile');
          return;
        }

        if (userDoc.data().role !== 'form_4_5') {
          alert("Access Denied: This manual entry page is strictly for Form 4 and Form 5 students.");
          navigate('/dashboard');
          return;
        }

        setPageState('ready');
      } catch (error) {
        console.error("Profile check failed:", error?.code || error);
        setPageState('error');
      }
    });

    return () => unsubscribe();
  }, [navigate]);

  const canAddRow = grades.length < MAX_SUBJECTS;

  const handleEditChange = (index, field, value) => {
    // Automatically convert grades and subjects to uppercase for clean database entry
    setGrades((rows) => rows.map((row, i) => (i === index ? { ...row, [field]: value.toUpperCase() } : row)));
  };

  const addEmptyRow = () => {
    if (!canAddRow) return;
    setGrades((rows) => [...rows, { subject: '', grade: '' }]);
  };

  // 2. UNIFIED DATABASE SAVING LOGIC
  const handleSaveAndProceed = async () => {
    const { error: validationError, results: cleanedResults } = validateGradeRows(grades);
    if (validationError) {
      alert(validationError);
      return;
    }

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

        alert("Your grades have been saved as you entered them. They have not been independently verified.");
        navigate('/ai-assessment'); // Routing straight to the cloud AI page
      }
    } catch (error) {
      console.error("Saving grades failed:", error?.code || error);
      alert("We couldn't save your grades. Please check your entries and try again.");
    }
  };

  if (pageState === 'missing-profile') {
    return (
      <StatusCard
        title="Student profile not found"
        text="We couldn't find your student profile, so your grades can't be saved yet. Please return to the dashboard, or sign in again if the problem continues."
        buttonLabel="Back to Dashboard"
        onAction={() => navigate('/dashboard')}
      />
    );
  }

  if (pageState === 'error') {
    return (
      <StatusCard
        title="Couldn't load your profile"
        text="We couldn't check your student profile right now. Please check your connection and try again."
        buttonLabel="Try again"
        onAction={() => window.location.reload()}
      />
    );
  }

  // Prevent UI flashing while checking the user's role
  if (pageState === 'loading') {
    return <div className="min-h-screen flex items-center justify-center font-bold text-gray-500">Loading your profile...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-3xl mx-auto bg-white rounded-3xl shadow-lg p-8">

       <Stepper currentStep={2} steps={['Interest', 'Enter Grades', 'AI Assessment', 'Recommendation', 'Preparation Plan']} />
        
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

        <button
          onClick={addEmptyRow}
          disabled={!canAddRow}
          className="mt-4 text-sm font-bold text-blue-600 hover:text-blue-800 transition disabled:text-gray-400 disabled:cursor-not-allowed"
        >
          + Add Elective Subject
        </button>
        {!canAddRow && (
          <p className="mt-1 text-xs text-gray-500">You can enter up to {MAX_SUBJECTS} subjects.</p>
        )}

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
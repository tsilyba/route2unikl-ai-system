// frontend/src/pages/user/UploadResults.jsx
//
// SPM results entry for SPM leavers (route: /upload-results).
//
// Automatic extraction of grades from a result-slip image is TEMPORARILY DISABLED
// (M1.5C deferred). The previous implementation called the Gemini API directly from
// the browser with an API key bundled into the frontend, which exposed the key; it has
// been removed and remains available in Git history (this file as of commit 3c48bec).
// Planned replacement: React -> authenticated FastAPI endpoint -> Gemini API, enabled
// only after a provider-terms and privacy review (see docs/PROJECT_STATUS.md).
// Until then students type their subjects and grades, and the results are saved with
// the manual-entry values accepted by firestore.rules.
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

const UploadResults = () => {
  // 'loading' | 'ready' | 'missing-profile' | 'error'
  const [pageState, setPageState] = useState('loading');
  const [gradeRows, setGradeRows] = useState(createBaseRows);

  const navigate = useNavigate();

  // Page access check (UX only; Firestore rules protect the data).
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

        if (userDoc.data().role !== 'spm_leaver') {
          alert("Access Denied: This results page is strictly for SPM Leavers.");
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

  const canAddRow = gradeRows.length < MAX_SUBJECTS;

  const handleEditChange = (index, field, value) => {
    setGradeRows((rows) => rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  };

  const addEmptyRow = () => {
    if (!canAddRow) return;
    setGradeRows((rows) => [...rows, { subject: '', grade: '' }]);
  };

  const handleConfirm = async () => {
    const { error: validationError, results: cleanedResults } = validateGradeRows(gradeRows);
    if (validationError) {
      alert(validationError);
      return;
    }

    try {
      const user = auth.currentUser;
      if (user) {
        const resultDocRef = doc(db, "results", user.uid);

        // Manual-entry values accepted by firestore.rules: the grades are typed by
        // the student and are not independently verified. (The rules have no
        // separate label for an SPM leaver's actual results; see docs/PROJECT_STATUS.md.)
        const dataToSave = {
          userId: user.uid,
          email: user.email,
          results: cleanedResults,
          updatedAt: new Date(),
          status: "manual_entry",
          recordType: "PREDICTED_GRADES",
          verificationMethod: "MANUAL_ENTRY"
        };

        await setDoc(resultDocRef, dataToSave);

        const userProfileRef = doc(db, "users", user.uid);
        await updateDoc(userProfileRef, { hasUploadedResults: true });

        alert("Your grades have been saved as you entered them. They have not been independently verified.");
        navigate('/ai-assessment');
      }
    } catch (error) {
      console.error("Saving results failed:", error?.code || error);
      alert("We couldn't save your results. Please check your entries and try again.");
    }
  };

  if (pageState === 'missing-profile') {
    return (
      <StatusCard
        title="Student profile not found"
        text="We couldn't find your student profile, so your results can't be saved yet. Please return to the dashboard, or sign in again if the problem continues."
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
      <div className="max-w-6xl mx-auto bg-white rounded-3xl shadow-lg p-8">

      <Stepper currentStep={2}/>


        <h2 className="text-2xl font-bold text-gray-800 mb-8">Enter your SPM results.</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="border-2 border-dashed border-gray-200 rounded-2xl p-8 flex flex-col items-center justify-center bg-gray-50 text-center" role="status">
            <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center text-3xl mb-4" aria-hidden="true">📂</div>
            <p className="text-gray-700 font-bold mb-2">Automatic slip reading is temporarily unavailable</p>
            <p className="text-sm text-gray-500">
              Reading grades from a photo of your result slip is switched off for now.
              Please type your subjects and grades in the form instead. Your results will be
              saved exactly as you enter them.
            </p>
          </div>

          <div className="bg-gray-50 rounded-2xl p-8 border border-gray-200 flex flex-col">
            <h3 className="text-xl font-bold text-gray-800 mb-2">Your SPM Results</h3>
            <p className="text-sm text-gray-500 mb-6">Enter each subject and grade from your result slip, then save.</p>

            <div className="flex-1 overflow-y-auto space-y-3 max-h-[400px] pr-2">
              <div className="flex gap-3 px-2 text-xs font-bold text-gray-400 uppercase tracking-wider">
                <div className="flex-1">Mata Pelajaran/Subject</div>
                <div className="w-16 text-center">Gred</div>
              </div>

             {gradeRows.map((item, idx) => (
                <div key={idx} className="flex gap-2 p-2 bg-white rounded-xl border shadow-sm">
                  <input
                    type="text"
                    value={item.subject}
                    placeholder="Mata Pelajaran"
                    readOnly={idx < 4}
                    onChange={(e) => handleEditChange(idx, 'subject', e.target.value.toUpperCase())}
                    className={`flex-1 p-2 border rounded-lg font-bold text-sm ${idx < 4 ? 'bg-gray-50/50' : 'bg-white'}`}
                  />

                  <input
                    type="text"
                    value={item.grade}
                    placeholder="Gred"
                    maxLength={2}
                    onChange={(e) => handleEditChange(idx, 'grade', e.target.value.toUpperCase())}
                    className="w-16 p-2 border rounded-lg text-center font-black text-blue-600 focus:ring-2 focus:ring-blue-400"
                  />
                </div>
              ))}
            </div>

            <button
              onClick={addEmptyRow}
              disabled={!canAddRow}
              className="mt-3 text-xs font-bold text-blue-600 hover:underline text-left pl-2 disabled:text-gray-400 disabled:no-underline disabled:cursor-not-allowed"
            >
              + Add Missing Elective
            </button>
            {!canAddRow && (
              <p className="mt-1 text-xs text-gray-500 pl-2">You can enter up to {MAX_SUBJECTS} subjects.</p>
            )}

            <button onClick={handleConfirm} className="mt-6 w-full py-3 bg-green-600 text-white font-bold rounded-xl shadow-lg hover:bg-green-700 transition">Confirm & Save</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UploadResults;

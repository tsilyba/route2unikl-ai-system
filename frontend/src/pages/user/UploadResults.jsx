import React, { useState, useRef, useEffect } from 'react';
import { GoogleGenerativeAI } from "@google/generative-ai";
import { db, auth } from '../../firebase';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore'; 
import { useNavigate } from 'react-router-dom';
import { onAuthStateChanged } from 'firebase/auth';
import Stepper from '../../components/Stepper';

const MIN_REQUIREMENTS = [
  { subject: 'BAHASA MELAYU', grade: '' },
  { subject: 'BAHASA INGGERIS', grade: '' },
  { subject: 'MATEMATIK', grade: '' },
  { subject: 'SEJARAH', grade: '' }
];

const genAI = new GoogleGenerativeAI(import.meta.env.VITE_GEMINI_API_KEY);

const UploadResults = () => {

  const [file, setFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [extractedResults, setExtractedResults] = useState([...MIN_REQUIREMENTS]);
  const [pageLoading, setPageLoading] = useState(true); // Added a loading state for the role check
  
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  // 1. UPDATED ROLE CHECK LOGIC
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
          

          if (userData.role !== 'spm_leaver') {
            alert("Access Denied: This OCR upload page is strictly for SPM Leavers.");
            navigate('/dashboard'); 
          } else {
            setPageLoading(false); 
          }
        }
      } catch (error) {
        console.error("Role verification failed:", error);
      }
    });

    return () => unsubscribe();
  }, [navigate]);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
      setExtractedResults([...MIN_REQUIREMENTS]);
    }
  };

  const fileToGenerativePart = async (file) => {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        resolve({
          inlineData: {
            data: reader.result.split(',')[1],
            mimeType: file.type
          },
        });
      };
      reader.readAsDataURL(file);
    });
  };

  const handleExtractWithAI = async () => {
    if (!file) return;
    setIsProcessing(true);

    try {
      const imagePart = await fileToGenerativePart(file);
      const model = genAI.getGenerativeModel({ model: "gemini-3.8-flash" });

      const prompt = `
        You are an expert academic transcript parser for Malaysian SPM results.
  
        1. Scan the image for ALL subjects and their letter grades.
        2. Subject Separation (CRITICAL):
     - "MATHEMATICS" / "MATEMATIK" must be output as "MATEMATIK".
     - "ADDITIONAL MATHEMATICS" / "MATEMATIK TAMBAHAN" must be output as "MATEMATIK TAMBAHAN".
     - Do NOT confuse them. They are two distinct subjects with separate grades.
      3. Language Normalization: Convert all subject names to standardized uppercase Bahasa Melayu:
     - "ENGLISH" / "BAHASA INGGERIS (CEFR)" -> "BAHASA INGGERIS"
     - "MALAY" / "BAHASA MALAYSIA" -> "BAHASA MELAYU"
     - "PHYSICS" -> "FIZIK"
     - "CHEMISTRY" -> "KIMIA"
     - "BIOLOGY" -> "BIOLOGI"
      4 . Grade Format: Extract ONLY the grade letters (A+, A, A-, B+, B, C+, C, D, E, G). Strip out words like "(CEMERLANG)" or "(KEPUJIAN)".
        
        Return strictly a JSON array: [{"subject": "...", "grade": "..."}]
      `;

      const result = await model.generateContent({
        contents: [
          {
            role: 'user',
            parts: [{ text: prompt }, imagePart],
          },
        ],
        generationConfig: { responseMimeType: "application/json" },
      });

      const responseText = result.response.text();
      const parsedJson = JSON.parse(responseText);

      mergeResultsWithUI(parsedJson);

    } catch (error) {
      console.error("AI Extractor Error:", error);
      alert("Extraction failed. Ensure your API key is correct.");
    } finally {
      setIsProcessing(false);
    }
  };

  const mergeResultsWithUI = (aiData) => {
    let currentResults = [...MIN_REQUIREMENTS];

    aiData.forEach((aiItem) => {
      const subject = (aiItem.subject || '').toUpperCase().trim();
      const grade = (aiItem.grade || '').toUpperCase().trim();

      const existingIndex = currentResults.findIndex(
        r => r.subject === subject || subject.includes(r.subject) || r.subject.includes(subject)
      );

      if (existingIndex !== -1) {
        currentResults[existingIndex].grade = grade;
      } else if (subject !== "") {
        currentResults.push({ subject, grade });
      }
    });

    setExtractedResults(currentResults);
  };

  const handleEditChange = (index, field, value) => {
    const newResults = [...extractedResults];
    newResults[index][field] = value;
    setExtractedResults(newResults);
  };

  const addEmptyRow = () => {
    setExtractedResults([...extractedResults, { subject: '', grade: '' }]);
  };

  // 2. UPDATED DATABASE SAVING LOGIC
  const handleConfirm = async () => {
    const mandatoryMissing = extractedResults.slice(0, 4).some(r => r.grade.trim() === '');
    if (mandatoryMissing) {
      alert("Please ensure BM, BI, Math, and Sejarah have grades.");
      return;
    }

    const cleanedResults = extractedResults.filter(r => r.subject.trim() !== '' && r.grade.trim() !== '');

    try {
      const user = auth.currentUser;
      if (user) {
        // Changed collection name to the generic 'results'
        const resultDocRef = doc(db, "results", user.uid);

        const dataToSave = {
          userId: user.uid,
          email: user.email,
          results: cleanedResults, 
          updatedAt: new Date(),
          status: "verified",
          recordType: "OFFICIAL_SPM_CERT", 
          verificationMethod: "AI_OCR_GEMINI" 
        };

        await setDoc(resultDocRef, dataToSave);

        const userProfileRef = doc(db, "users", user.uid);
        await updateDoc(userProfileRef, { hasUploadedResults: true });

        alert("Results securely verified and saved to database!");
        navigate('/ai-assessment');
      }
    } catch (error) {
      console.error("Firestore Save Error:", error);
      alert("Failed to save. Check your Firestore Rules.");
    }
  };

  // Prevent UI flashing while checking the user's role
  if (pageLoading) {
    return <div className="min-h-screen flex items-center justify-center font-bold text-gray-500">Verifying Security Credentials...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-6xl mx-auto bg-white rounded-3xl shadow-lg p-8">
        
      <Stepper currentStep={2}/>


        <h2 className="text-2xl font-bold text-gray-800 mb-8">Upload your SPM result.</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="border-2 border-dashed border-blue-200 rounded-2xl p-8 flex flex-col items-center justify-center bg-blue-50/30">
            <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center text-3xl mb-4">📂</div>
            <p className="text-gray-600 font-semibold mb-4">Upload Here</p>

            <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleFileChange} />
            <button 
              onClick={() => fileInputRef.current.click()}
              className="px-6 py-2 bg-white border border-blue-200 text-blue-600 font-bold rounded-xl shadow-sm hover:bg-blue-50 transition"
            >
              Select Result Slip Image
            </button>

            {file && (
              <div className="mt-6 w-full">
                <p className="text-xs text-gray-400 mb-2 truncate">File ready: {file.name}</p>
                <button 
                  onClick={handleExtractWithAI}
                  disabled={isProcessing}
                  className="w-full py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 disabled:bg-gray-300 transition flex justify-center items-center gap-2 shadow-lg"
                >
                  {isProcessing ? (
                    <>
                      <span className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></span>
                      Loading...
                    </>
                  ) : "Analyze Slip"}
                </button>
              </div>
            )}
          </div>

          <div className="bg-gray-50 rounded-2xl p-8 border border-gray-200 flex flex-col">
            <h3 className="text-xl font-bold text-gray-800 mb-2">Results Preview</h3>
            <p className="text-sm text-gray-500 mb-6">Verify the subject and grades extracted before saving.</p>

            <div className="flex-1 overflow-y-auto space-y-3 max-h-[400px] pr-2">
              <div className="flex gap-3 px-2 text-xs font-bold text-gray-400 uppercase tracking-wider">
                <div className="flex-1">Mata Pelajaran/Subject</div>
                <div className="w-16 text-center">Gred</div>
              </div>

             {extractedResults.map((item, idx) => (
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

            <button onClick={addEmptyRow} className="mt-3 text-xs font-bold text-blue-600 hover:underline text-left pl-2">+ Add Missing Elective</button>

            <button onClick={handleConfirm} className="mt-6 w-full py-3 bg-green-600 text-white font-bold rounded-xl shadow-lg hover:bg-green-700 transition">Confirm & Save</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UploadResults;
import React, { useState, useRef, useEffect } from 'react';
import { GoogleGenerativeAI } from "@google/generative-ai";
import { db, auth } from '../../firebase';
import { doc, setDoc, updateDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';
import { onAuthStateChanged } from 'firebase/auth';

// 1. Updated Requirements (No KOD)
const MIN_REQUIREMENTS = [
  { subject: 'BAHASA MELAYU', grade: '' },
  { subject: 'BAHASA INGGERIS', grade: '' },
  { subject: 'MATEMATIK', grade: '' },
  { subject: 'SEJARAH', grade: '' }
];

const genAI = new GoogleGenerativeAI("AIzaSyAEHlYHat-5A0PjGjlGiDawA5qh73yGCT4");

const UploadResults = () => {


  const [file, setFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [extractedResults, setExtractedResults] = useState([...MIN_REQUIREMENTS]);
  
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (!auth.currentUser) {
        navigate('/login');
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
      const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });

      const prompt = `
        You are a universal academic transcript parser for Malaysian SPM results. 
        1. Scan the image for ALL subjects and grades.
        2. Language Independence: Identify subjects even if written in English (e.g., "MATHEMATICS" -> "MATEMATIK").
        3. Strict Grade Format: Extract ONLY the grade symbol (A+, A, A-, B+, B, C+, C, D, E, G). 
        4. Standardize: Convert all subject names to standard BAHASA MELAYU uppercase.
        
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

  // 2. Updated Merging Logic (Matched by Subject Name only)
  const mergeResultsWithUI = (aiData) => {
    let currentResults = [...MIN_REQUIREMENTS];

    aiData.forEach((aiItem) => {
      const subject = (aiItem.subject || '').toUpperCase().trim();
      const grade = (aiItem.grade || '').toUpperCase().trim();

      // Check if AI subject matches or is similar to our 4 mandatory ones
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

  // 3. Updated Database Logic
  const handleConfirm = async () => {
    // Validate mandatory 4
    const mandatoryMissing = extractedResults.slice(0, 4).some(r => r.grade.trim() === '');
    if (mandatoryMissing) {
      alert("Please ensure BM, BI, Math, and Sejarah have grades.");
      return;
    }

    const cleanedResults = extractedResults.filter(r => r.subject.trim() !== '' && r.grade.trim() !== '');

    try {
      const user = auth.currentUser;
      if (user) {
        // Save to dedicated spm_results collection
        const resultDocRef = doc(db, "spm_results", user.uid);

        const dataToSave = {
          userId: user.uid,
          email: user.email,
          results: cleanedResults, // Array of {subject, grade}
          updatedAt: new Date(),
          status: "verified"
        };

        await setDoc(resultDocRef, dataToSave);

        // Update user profile flag
        const userProfileRef = doc(db, "users", user.uid);
        await updateDoc(userProfileRef, { hasUploadedResults: true });

        alert("Results saved to database! 🎉");
        navigate('/ai-assessment');
      }
    } catch (error) {
      console.error("Firestore Save Error:", error);
      alert("Failed to save. Check your Firestore Rules.");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-6xl mx-auto bg-white rounded-3xl shadow-lg p-8">
        
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

        <h2 className="text-2xl font-bold text-gray-800 mb-8">Upload your SPM result.</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="border-2 border-dashed border-blue-200 rounded-2xl p-8 flex flex-col items-center justify-center bg-blue-50/30">
            <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center text-3xl mb-4">✨</div>
            <p className="text-gray-600 font-semibold mb-4">AI Multimodal Vision Engine</p>

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
                      AI is scanning your document...
                    </>
                  ) : "Analyze Slip with Gemini AI"}
                </button>
              </div>
            )}
          </div>

          <div className="bg-gray-50 rounded-2xl p-8 border border-gray-200 flex flex-col">
            <h3 className="text-xl font-bold text-gray-800 mb-2">Results Preview</h3>
            <p className="text-sm text-gray-500 mb-6">Verify the data extracted by the AI below before saving.</p>

            <div className="flex-1 overflow-y-auto space-y-3 max-h-[400px] pr-2">
              <div className="flex gap-3 px-2 text-xs font-bold text-gray-400 uppercase tracking-wider">
                <div className="flex-1">Mata Pelajaran</div>
                <div className="w-16 text-center">Gred</div>
              </div>

             {extractedResults.map((item, idx) => (
  <div key={idx} className="flex gap-2 p-2 bg-white rounded-xl border shadow-sm">
    {/* SUBJECT NAME INPUT */}
    <input 
      type="text" 
      value={item.subject} 
      placeholder="Mata Pelajaran" 
      // If it's the core 4 subjects, it's readOnly. 
      // Otherwise, we allow the user to edit elective names.
      readOnly={idx < 4} 
      onChange={(e) => handleEditChange(idx, 'subject', e.target.value.toUpperCase())}
      className={`flex-1 p-2 border rounded-lg font-bold text-sm ${idx < 4 ? 'bg-gray-50/50' : 'bg-white'}`}
    />

    {/* GRADE INPUT */}
    <input 
      type="text" 
      value={item.grade} 
      placeholder="Gred" 
      maxLength={2}
      // This MUST have an onChange so users can fix AI mistakes
      onChange={(e) => handleEditChange(idx, 'grade', e.target.value.toUpperCase())}
      className="w-16 p-2 border rounded-lg text-center font-black text-blue-600 focus:ring-2 focus:ring-blue-400"
    />
  </div>
))}
            </div>

            <button onClick={addEmptyRow} className="mt-3 text-xs font-bold text-blue-600 hover:underline text-left pl-2">+ Add Missing Elective</button>

            <button onClick={handleConfirm} className="mt-6 w-full py-3 bg-green-600 text-white font-bold rounded-xl shadow-lg hover:bg-green-700 transition">Confirm & Save to Firestore</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UploadResults;
import React, { useState, useEffect } from 'react';
import { db, auth } from '../../firebase';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';
import { onAuthStateChanged } from 'firebase/auth';

const DummyAIAssessment = () => {
  const [loading, setLoading] = useState(true);
  const [questions, setQuestions] = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedAnswers, setSelectedAnswers] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  // Storage for the final database save
  const [userData, setUserData] = useState({ role: '', grades: [], interests: [] });
  
  const navigate = useNavigate();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (!user) {
        navigate('/login');
        return;
      }
      await fetchProfileAndBuildMockQuiz(user.uid);
    });

    return () => unsubscribe();
  }, [navigate]);

  const fetchProfileAndBuildMockQuiz = async (uid) => {
    try {
      // 1. Fetch data from BOTH unified collections
      const userDocRef = doc(db, "users", uid);
      const resultsDocRef = doc(db, "results", uid); // Pointing to your new unified collection!

      const [userSnap, resultsSnap] = await Promise.all([
        getDoc(userDocRef),
        getDoc(resultsDocRef)
      ]);

      if (!userSnap.exists() || !resultsSnap.exists()) {
        alert("Missing profile data. Please complete the previous steps.");
        navigate('/dashboard');
        return;
      }

      const uData = userSnap.data();
      const rData = resultsSnap.data();

      const interests = uData.chosenInterests || ["General Studies"];
      const grades = rData.results || [];
      const role = uData.role || "unknown";

      // Store them in state so we can attach them to the final save
      setUserData({ role, grades, interests });

      // 2. Generate the "Fake AI" Questions
      buildDynamicMockQuestions(interests, grades);

    } catch (error) {
      console.error("Error setting up demo assessment:", error);
      setLoading(false);
    }
  };

  const buildDynamicMockQuestions = (interests, grades) => {
    // Grab their top interest and top subject to make it feel personalized
    const primaryInterest = interests.length > 0 ? interests[0] : "your chosen field";
    const topSubject = grades.length > 0 ? grades[0].subject : "your core subjects";

    // 5 General, non-complex questions that inject the user's actual data
    const generatedQuestions = [
      {
        category: primaryInterest,
        question: `As someone interested in ${primaryInterest}, how would you prioritize tasks if you were assigned a major group project?`,
        options: [
          "Do all the work myself to ensure quality.",
          "Divide tasks based on team members' strengths.",
          "Wait for the leader to tell me what to do.",
          "Pick the easiest task first."
        ],
        correctIndex: 1
      },
      {
        category: primaryInterest,
        question: `In the field of ${primaryInterest}, technology changes rapidly. How do you adapt to learning a new system?`,
        options: [
          "Read the official documentation and practice.",
          "Stick to the old system as long as possible.",
          "Ask someone else to do it for me.",
          "Ignore it until it becomes mandatory."
        ],
        correctIndex: 0
      },
      {
        category: "General Logic",
        question: `Applying that logical thinking, what is the best way to troubleshoot a recurring error?`,
        options: [
          "Restart the process repeatedly.",
          "Identify the pattern of when the error occurs.",
          "Delete the project and start over.",
          "Assume it is a hardware issue."
        ],
        correctIndex: 1
      },
      {
        category: "Professionalism",
        question: "You have a strict deadline tomorrow, but you discover a minor flaw in your work. What do you do?",
        options: [
          "Submit it and hope no one notices.",
          "Fix it immediately, even if it takes extra time.",
          "Blame the flaw on a team member.",
          "Ask for a one-week extension."
        ],
        correctIndex: 1
      },
      {
        category: "Problem Solving",
        question: "When faced with a complex scenario that you don't immediately understand, what is your first step?",
        options: [
          "Give up and choose a different path.",
          "Break the complex problem down into smaller, manageable pieces.",
          "Guess the answer to save time.",
          "Search for the exact answer online without understanding it."
        ],
        correctIndex: 1
      }
    ];

    setQuestions(generatedQuestions);
    setLoading(false);
  };

  const handleOptionSelect = (optionIdx) => {
    setSelectedAnswers({
      ...selectedAnswers,
      [currentIdx]: optionIdx
    });
  };

  const handleNext = async () => {
    if (selectedAnswers[currentIdx] === undefined) {
      alert("Please select an option before moving forward.");
      return;
    }

    if (currentIdx < questions.length - 1) {
      setCurrentIdx(currentIdx + 1);
    } else {
      await saveAssessmentAndProceed();
    }
  };

  const saveAssessmentAndProceed = async () => {
    setIsSubmitting(true);
    try {
      const user = auth.currentUser;
      if (user) {
        const assessmentDocRef = doc(db, "ai_assessments", user.uid);
        
        const detailedAnswers = questions.map((q, idx) => ({
          category: q.category,
          question: q.question,
          selectedOption: q.options[selectedAnswers[idx]],
          isCorrect: selectedAnswers[idx] === q.correctIndex
        }));

        const performanceBreakdown = {};
        detailedAnswers.forEach(ans => {
          performanceBreakdown[ans.category] = ans.isCorrect ? 1 : 0;
        });

        // 3. Save EVERYTHING back to the database
        await setDoc(assessmentDocRef, {
          userId: user.uid,
          userRole: userData.role,           // Saving the role
          academicSnapshot: userData.grades, // Saving the grades payload
          answers: detailedAnswers,
          scoresByPathway: performanceBreakdown,
          completedAt: new Date(),
          isDemoMode: true                   // Flag for your presentation
        });

        const userProfileRef = doc(db, "users", user.uid);
        await updateDoc(userProfileRef, { currentStep: 3 });

        alert("Demo Assessment complete! Processing metrics... 🎉");
        navigate('/recommendation');
      }
    } catch (error) {
      console.error("Error saving assessment answers:", error);
      alert("Failed to save. Check your console.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col justify-center items-center bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-blue-600 mb-4"></div>
        <p className="text-gray-600 font-bold">Generating personalized presentation mock...</p>
      </div>
    );
  }

  const currentQuestion = questions[currentIdx];

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-3xl mx-auto bg-white rounded-3xl shadow-lg p-8">
        
        {/* Stepper Header indicator */}
        <div className="flex justify-between items-center mb-8 text-sm font-bold text-gray-400">
          <span>{currentQuestion.category} <span className="text-blue-400 ml-2">(Demo Mode)</span></span>
          <span className="text-blue-600">Question {currentIdx + 1} of {questions.length}</span>
        </div>

        <div className="w-full bg-gray-100 h-2 rounded-full mb-8 overflow-hidden">
          <div 
            className="bg-blue-600 h-full transition-all duration-300" 
            style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
          />
        </div>

        {currentQuestion && (
          <div>
            <h3 className="text-xl font-bold text-gray-800 mb-6">{currentQuestion.question}</h3>
            
            <div className="space-y-3">
              {currentQuestion.options.map((option, oIdx) => (
                <button
                  key={oIdx}
                  onClick={() => handleOptionSelect(oIdx)}
                  className={`w-full p-4 text-left rounded-xl border-2 transition font-medium
                    ${selectedAnswers[currentIdx] === oIdx 
                      ? 'border-blue-500 bg-blue-50 text-blue-700 font-bold' 
                      : 'border-gray-200 hover:border-blue-200 bg-white text-gray-700'
                    }`}
                >
                  {option}
                </button>
              ))}
            </div>

            <div className="mt-8 flex justify-end">
              <button
                onClick={handleNext}
                disabled={isSubmitting}
                className="px-8 py-3 bg-blue-600 text-white font-bold rounded-xl hover:bg-blue-700 shadow-md transition disabled:bg-gray-300"
              >
                {isSubmitting ? "Saving..." : currentIdx === questions.length - 1 ? "Submit Assessment" : "Next Question"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DummyAIAssessment;
import React, { useState, useEffect } from 'react';
import { db, auth } from '../../firebase'; // 1. Added auth import
import { collection, getDocs, doc, getDoc } from 'firebase/firestore'; // 2. Added doc and getDoc imports
import { useNavigate } from 'react-router-dom';
import { onAuthStateChanged } from 'firebase/auth'; // 3. Added auth listener

const Dashboard = () => {
  const [programs, setPrograms] = useState([]); 
  const [loading, setLoading] = useState(true); 
  const [error, setError] = useState(null);
  
  // 4. NEW STATE: Track the user's role
  const [userRole, setUserRole] = useState(null); 
  
  const navigate = useNavigate();

  // 5. NEW EFFECT: Fetch the user's role when the dashboard loads
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (user) {
        try {
          const userDoc = await getDoc(doc(db, "users", user.uid));
          if (userDoc.exists()) {
            setUserRole(userDoc.data().role); // Save the role (e.g., 'spm_leaver' or 'form_4_5')
          }
        } catch (err) {
          console.error("Error fetching user role:", err);
        }
      }
    });

    return () => unsubscribe();
  }, []);

  // Fetch Programs Effect (unchanged)
  useEffect(() => {
    const fetchPrograms = async () => {
      try {
        const querySnapshot = await getDocs(collection(db, 'programs')); 
        const programsList = querySnapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data(),
        }));

        setPrograms(programsList);
        setLoading(false);
      } catch (error) {
        console.error('Error fetching programs:', error);
        setError(error.message);
        setLoading(false);
      }
    };

    fetchPrograms();
  }, []);

  // 6. THE TRAFFIC COP FUNCTION: Routes the user based on their state
  const handleStartAssessment = () => {
    if (!userRole) {
      alert("Still verifying your account details. Please wait a moment.");
      return;
    }

    if (userRole === 'spm_leaver') {
      navigate('/upload-results');
    } else if (userRole === 'form_4_5') {
      navigate('/manual-grade-entry');
    } else {
      alert("Role not recognized. Please contact support.");
    }
  };

  if (error) {
    return <div className="p-10 text-red-500">Error: {error}</div>;
  }

  if (loading) {
    return <div className="p-10 text-center font-bold text-blue-600">Loading...</div>;
  }

  return (
    <div className="py-12 px-4">
      <div className="mx-auto bg-white rounded-2xl shadow-xl w-full max-w-6xl border border-gray-100 overflow-hidden">
        
        {/* Welcome Section */}
        <div className="text-center p-12 bg-white">
          <h2 className="text-4xl font-extrabold mb-4 text-blue-600">Ready to discover your best path?</h2>
          <p className="text-lg text-gray-600 mb-8 max-w-2xl mx-auto">
            Your journey to UniKL starts here.
          </p>
          
          {/* 7. UPDATED BUTTON: Now calls our smart routing function */}
          <button 
            onClick={handleStartAssessment} 
            className="bg-blue-600 text-white px-8 py-4 rounded-xl font-bold hover:bg-blue-700 transition-all shadow-lg hover:shadow-blue-200"
          >
           Start Assessment
          </button>
        </div>

        {/* Programs Offered Section */}
        <div className="p-8 border-t border-gray-50">
          <div className="flex justify-between items-end mb-8">
            <div>
              <h3 className="text-2xl font-bold text-gray-800">Programs Available at UniKL</h3>
              <p className="text-gray-500 text-sm">Explore programs across our 12 campuses</p>
            </div>
          </div>

          {/* HORIZONTAL SCROLL CONTAINER */}
          <div className="flex overflow-x-auto pb-8 space-x-6 snap-x snap-mandatory">
            {programs.length === 0 ? (
              <p className="text-gray-400 italic">No programs available at the moment.</p>
            ) : (
              <>
                {/* Display only the first 6 programs */}
                {programs.slice(0, 6).map((program) => (
                  <div 
                    key={program.id} 
                    className="snap-start min-w-[300px] max-w-[300px] p-6 bg-blue-50/50 rounded-2xl border border-blue-100 shadow-sm flex flex-col justify-between"
                  >
                    <div>
                      <div className="w-10 h-10 bg-white rounded-lg flex items-center justify-center shadow-sm mb-4">
                        <span className="text-xl">🎓</span> 
                      </div>
                      <h4 className="text-lg font-bold text-blue-900 leading-tight mb-2">{program.title}</h4>
                      <p className="text-gray-600 text-sm mb-4 line-clamp-3">{program.short_description}</p>
                      <p className="text-xs font-bold text-blue-400 uppercase tracking-wider">Specialisation</p>
                      <p className="text-sm text-gray-700">{program.specialisation}</p>
                    </div>
                    <a href={program.link} target="_blank" rel="noreferrer" className="mt-6 text-blue-600 font-bold text-sm hover:underline">
                      Learn More
                    </a>
                  </div>
                ))}

                {/* The "View All" Card at the end */}
                <div 
                  onClick={() => navigate('/all-programs')}
                  className="snap-start min-w-[200px] max-w-[200px] flex flex-col items-center justify-center bg-white border-2 border-dashed border-blue-200 rounded-2xl cursor-pointer hover:bg-blue-50 transition-colors group"
                >
                  <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                    <span className="text-blue-600 text-2xl">→</span>
                  </div>
                  <p className="font-bold text-blue-600">View All</p>
                  <p className="text-xs text-gray-400">{programs.length} Programs</p>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
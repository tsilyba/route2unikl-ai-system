import React, { useState, useEffect } from 'react';
import { db, auth } from '../../firebase';
import { useNavigate } from 'react-router-dom';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';
import { onAuthStateChanged } from 'firebase/auth';
import Stepper from '../../components/Stepper';

const INTEREST_FIELDS = [
  {
    id: 'computing',
    title: 'Computing & Digital Technology',
    description: 'Software, Networking, Multimedia, Animation, and digital systems.',
    categoryName: 'Computing & Digital Technology',
    bgLight: 'bg-blue-50',
    iconColor: 'text-blue-600',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 8l-2 2 2 2m4-4l2 2-2 2" />
      </svg>
    )
  },
  {
    id: 'engineering',
    title: 'Engineering & Technology',
    description: 'Electrical , Mechanical, Automation, Manufacturing, and Engineering Technology',
    categoryName: 'Engineering & Technology',
    bgLight: 'bg-blue-50',
    iconColor: 'text-blue-600',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    )
  },
  {
    id: 'aviation',
    title: 'Aviation, Automotive & Transportation',
    description: 'Aircraft, Automotive, Railway, and Transportation Technology',
    categoryName: 'Aviation, Automotive & Transportation',
    bgLight: 'bg-blue-50',
    iconColor: 'text-blue-600',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
      </svg>
    )
  },
  {
    id: 'maritime',
    title: 'Marine & Maritime',
    description: 'Shipbuilding, Maritime Systems, Maritime Operations and Naval',
    categoryName: 'Marine & Maritime',
    bgLight: 'bg-cyan-50',
    iconColor: 'text-cyan-600',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10l2 1 2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 20h18M5 12h14" />
      </svg>
    )
  },
  {
    id: 'chemical',
    title: 'Chemical & Food Technology',
    description: 'Chemical Processes, Food Production, and Industrial Technology',
    categoryName: 'Chemical & Food Technology',
    bgLight: 'bg-emerald-50',
    iconColor: 'text-emerald-600',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 7H9L8 4z" />
      </svg>
    )
  },
  {
    id: 'health',
    title: 'Health & Medical Sciences',
    description: 'Medicine, Pharmacy, Nursing, Laboratory, Imaging , and healthcare',
    categoryName: 'Health & Medical Sciences',
    bgLight: 'bg-rose-50',
    iconColor: 'text-rose-500',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
      </svg>
    )
  },
  {
    id: 'business',
    title: 'Business Management & Logistics',
    description: 'Business, Management, Operations, and Supply Chain',
    categoryName: 'Business Management & Logistics',
    bgLight: 'bg-amber-50',
    iconColor: 'text-amber-600',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    )
  },
  {
    id: 'creative',
    title: 'Creative, Arts, Design & Multimedia',
    description: 'Design , Animation, Multimedia, Creative Arts , and Visual Content',
    categoryName: 'Creative, Arts, Design & Multimedia',
    bgLight: 'bg-purple-50',
    iconColor: 'text-purple-600',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4 4 4 0 014-4c.7 0 1.34.18 1.9.5A7.96 7.96 0 0115 11a8 8 0 018 8v1a2 2 0 01-2 2H7z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 7a2 2 0 100-4 2 2 0 000 4zm4 4a2 2 0 100-4 2 2 0 000 4zm-8 0a2 2 0 100-4 2 2 0 000 4z" />
      </svg>
    )
  }
];

const InterestSelection = () => {
  const [selectedFields, setSelectedFields] = useState([]);
  const [userRole, setUserRole] = useState('spm_leaver');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (!user) {
        navigate('/login');
        return;
      }

      try {
        const userDoc = await getDoc(doc(db, 'users', user.uid));
        if (userDoc.exists()) {
          const data = userDoc.data();
          if (data.role) setUserRole(data.role);
          if (data.chosenInterests && Array.isArray(data.chosenInterests)) {
            setSelectedFields(data.chosenInterests);
          }
        }
      } catch (err) {
        console.error('Error fetching user profile:', err);
      } finally {
        setLoading(false);
      }
    });

    return () => unsubscribe();
  }, [navigate]);

  const toggleInterest = (title) => {
    if (selectedFields.includes(title)) {
      setSelectedFields(selectedFields.filter((item) => item !== title));
    } else {
      if (selectedFields.length >= 2) {
        alert('You can select up to 2 academic fields only.');
        return;
      }
      setSelectedFields([...selectedFields, title]);
    }
  };

  const handleProceed = async () => {
    if (selectedFields.length === 0) {
      alert('Please select at least 1 academic field that interests you.');
      return;
    }

    setSaving(true);
    try {
      const user = auth.currentUser;
      if (user) {
        await updateDoc(doc(db, 'users', user.uid), {
          chosenInterests: selectedFields,
          currentStep: 2,
          hasCompletedProfile: true,
          updatedAt: new Date()
        });

        // Route according to user role
        if (userRole === 'form_4_5' || userRole === 'upper_secondary') {
          navigate('/manual-grade-entry');
        } else {
          navigate('/upload-results');
        }
      }
    } catch (err) {
      console.error('Error saving selected interests:', err);
      alert('Failed to save selection. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 text-gray-500 font-bold">
        Loading profile...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F0F5FD] py-6 px-4 md:px-8">
      {/* Top Navbar */}
     
      {/* Main Container Card[cite: 23] */}
      <main className="max-w-6xl mx-auto bg-white rounded-[2.5rem] shadow-xl p-8 md:p-12 border border-gray-100">
        
        <Stepper currentStep={1}/>

        {/* Section Header with Robot Mascot[cite: 23] */}
        <section className="flex items-start gap-4 mb-10">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-100 border border-blue-200 flex items-center justify-center text-3xl shadow-sm shrink-0">
            🤖
          </div>
          <div>
            <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 tracking-tight">
              What Field Are You Interested In ?
            </h1>
            <p className="text-gray-500 text-sm mt-1 leading-relaxed">
              Select up to <strong className="text-gray-700">2 academic fields</strong> that interest you the most .
              <br className="hidden md:block" />
              We will use your interest together with your SPM results to recommend suitable UniKL programmes.
            </p>
          </div>
        </section>

        {/* 8-Card Interest Grid[cite: 23] */}
        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {INTEREST_FIELDS.map((field) => {
            const isSelected = selectedFields.includes(field.title);
            return (
              <div
                key={field.id}
                role="button"
                tabIndex={0}
                onClick={() => toggleInterest(field.title)}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && toggleInterest(field.title)}
                className={`relative flex items-start gap-4 p-5 rounded-3xl border-2 cursor-pointer transition-all duration-200 text-left outline-none ${
                  isSelected
                    ? 'border-[#0B3996] bg-blue-50/20 shadow-md ring-2 ring-blue-100'
                    : 'border-gray-100 hover:border-gray-200 bg-white shadow-sm hover:shadow'
                }`}
              >
                {/* Radio/Check Indicator[cite: 23] */}
                <div
                  className={`absolute top-5 right-5 w-5 h-5 rounded-full border flex items-center justify-center transition-all ${
                    isSelected
                      ? 'border-[#0B3996] bg-[#0B3996]'
                      : 'border-gray-300 bg-white'
                  }`}
                >
                  {isSelected && <div className="w-2 h-2 rounded-full bg-white" />}
                </div>

                {/* Field Icon Badge[cite: 23] */}
                <div
                  className={`w-12 h-12 rounded-2xl ${field.bgLight} ${field.iconColor} flex items-center justify-center shrink-0 border border-white shadow-inner`}
                >
                  {field.icon}
                </div>

                {/* Content[cite: 23] */}
                <div className="pr-6">
                  <h2 className="font-bold text-gray-900 text-sm leading-snug">
                    {field.title}
                  </h2>
                  <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                    {field.description}
                  </p>
                </div>
              </div>
            );
          })}
        </section>

        {/* Bottom Action Footer */}
        <footer className="mt-12 pt-6 border-t border-gray-100 flex flex-col sm:flex-row justify-between items-center gap-4">
          <div className="text-xs font-semibold text-gray-500">
            Selected: <span className="text-[#0B3996] font-bold">{selectedFields.length}</span> of 2 fields
          </div>
          <button
            type="button"
            onClick={handleProceed}
            disabled={saving}
            className="w-full sm:w-auto px-10 py-3.5 bg-[#0B3996] hover:bg-blue-800 text-white font-bold text-sm rounded-2xl shadow-lg shadow-blue-900/10 transition-all disabled:bg-gray-300"
          >
            {saving ? 'Saving...' : 'Next: Academic Results →'}
          </button>
        </footer>

      </main>
    </div>
  );
};

export default InterestSelection;
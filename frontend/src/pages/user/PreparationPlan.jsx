import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { db, auth } from '../../firebase';
import { doc, updateDoc } from 'firebase/firestore';
import { onAuthStateChanged } from 'firebase/auth';
import Stepper from '../../components/Stepper';
import testplanData from '../../assets/unikl_foundation_testplan.json';

const getPlatformStyle = (platform = '') => {
  const p = platform.toLowerCase();
  if (p.includes('youtube')) {
    return { bg: 'bg-red-100 text-red-700', icon: '▶' };
  }
  if (p.includes('freecodecamp')) {
    return { bg: 'bg-purple-100 text-purple-700', icon: '💻' };
  }
  if (p.includes('openstax')) {
    return { bg: 'bg-blue-100 text-blue-700', icon: '📘' };
  }
  if (p.includes('openlearn')) {
    return { bg: 'bg-indigo-100 text-indigo-700', icon: '🏛️' };
  }
  if (p.includes('khan academy')) {
    return { bg: 'bg-emerald-100 text-emerald-700', icon: '🌱' };
  }
  if (p.includes('geeksforgeeks')) {
    return { bg: 'bg-green-100 text-green-800', icon: '⚡' };
  }
  if (p.includes('mit')) {
    return { bg: 'bg-rose-100 text-rose-700', icon: '🎓' };
  }
  if (p.includes('cisco') || p.includes('microsoft')) {
    return { bg: 'bg-cyan-100 text-cyan-800', icon: '🌐' };
  }
  if (p.includes('alison')) {
    return { bg: 'bg-teal-100 text-teal-800', icon: '📖' };
  }
  return { bg: 'bg-amber-100 text-amber-800', icon: '🎓' };
};

const PreparationPlan = () => {
  const [selectedProgram, setSelectedProgram] = useState(null);
  const [levelFilter, setLevelFilter] = useState('Foundation');
  const [completedItems, setCompletedItems] = useState({});
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (!user) {
        navigate('/login');
        return;
      }

      // Read programId from URL query or localStorage
      const params = new URLSearchParams(location.search);
      const queryId = params.get('programId');
      const savedId = localStorage.getItem('selected_prep_program_id');
      const targetId = queryId || savedId || 'unikl_miit_foundation_computer';

      const found = testplanData.find(p => p.program_id === targetId) || testplanData[0];
      setSelectedProgram(found);
      if (found?.level) {
        setLevelFilter(found.level);
      }

      // Save step 5 completion to Firestore
      try {
        const userRef = doc(db, 'users', user.uid);
        await updateDoc(userRef, { currentStep: 5, hasCompletedPreparationPlan: true });
      } catch (e) {
        console.warn('Could not update profile step:', e);
      }

      setLoading(false);
    });

    return () => unsubscribe();
  }, [location.search, navigate]);

  const handleSelectProgram = (prog) => {
    setSelectedProgram(prog);
    setLevelFilter(prog.level);
    setCompletedItems({});
    localStorage.setItem('selected_prep_program_id', prog.program_id);
  };

  const toggleCheck = (idx) => {
    setCompletedItems(prev => ({
      ...prev,
      [idx]: !prev[idx]
    }));
  };

  if (loading || !selectedProgram) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-blue-600 mb-4"></div>
      </div>
    );
  }

  const guidelines = selectedProgram.preparatory_guideline || [];
  const totalItems = guidelines.length;
  const completedCount = Object.values(completedItems).filter(Boolean).length;
  const progressPercent = totalItems > 0 ? Math.round((completedCount / totalItems) * 100) : 0;

  const filteredProgramsByLevel = testplanData.filter(p => p.level === levelFilter);

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-6xl mx-auto bg-white rounded-3xl shadow-lg p-6 md:p-10 border border-gray-100">

        {/* Step 5 Stepper */}
        <Stepper currentStep={5} />

        {/* Header */}
        <div className="text-center max-w-3xl mx-auto mb-8">
          <span className="bg-emerald-100 text-emerald-800 px-4 py-1.5 rounded-full text-xs font-extrabold uppercase tracking-wider">
            Step 5 • Academic Readiness
          </span>
          <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 mt-3 tracking-tight">
            Personalized Academic Preparation Plan
          </h1>
          <p className="text-gray-500 text-sm mt-2 leading-relaxed">
            Bridge the transition from secondary school to university level. Complete these curated online learning
            modules before orientation to excel in your UniKL coursework.
          </p>
        </div>

        {/* LEVEL SWITCHER & PROGRAMME SELECTOR */}
        <div className="bg-gray-50 p-5 rounded-3xl border border-gray-100 mb-8">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-4 mb-4">
            <div className="flex items-center gap-2">
              {['Foundation', 'Diploma'].map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setLevelFilter(lvl)}
                  className={`px-4 py-2 rounded-xl text-xs font-extrabold transition cursor-pointer ${
                    levelFilter === lvl
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-100'
                  }`}
                >
                  {lvl} Programmes ({testplanData.filter(p => p.level === lvl).length})
                </button>
              ))}
            </div>

            <div className="w-full sm:w-80">
              <select
                value={selectedProgram.program_id}
                onChange={(e) => {
                  const found = testplanData.find(p => p.program_id === e.target.value);
                  if (found) handleSelectProgram(found);
                }}
                className="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-xs font-bold text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {testplanData.map((p) => (
                  <option key={p.program_id} value={p.program_id}>
                    [{p.level}] {p.title} ({p.campuses})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 max-h-36 overflow-y-auto pr-1">
            {filteredProgramsByLevel.map((prog) => {
              const isSelected = prog.program_id === selectedProgram.program_id;
              return (
                <button
                  key={prog.program_id}
                  onClick={() => handleSelectProgram(prog)}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                    isSelected
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-white text-gray-600 border border-gray-200 hover:border-blue-300'
                  }`}
                >
                  <span>{prog.title}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${isSelected ? 'bg-blue-700 text-blue-100' : 'bg-gray-100 text-gray-500'}`}>
                    {prog.campuses}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* PROGRAM BANNER & READINESS PROGRESS */}
        <div className="bg-gradient-to-r from-blue-50 via-indigo-50/50 to-blue-50 rounded-3xl p-6 md:p-8 border border-blue-100 mb-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold text-blue-600 uppercase tracking-wider mb-1">
              <span>{selectedProgram.level} Pathway</span>
              <span>•</span>
              <span>{selectedProgram.campuses}</span>
            </div>
            <h2 className="text-2xl font-extrabold text-gray-900">
              {selectedProgram.title}
            </h2>
            <p className="text-gray-600 text-xs mt-1 max-w-xl">
              Specialisation: <strong className="text-gray-800">{selectedProgram.specialisation}</strong> | 
              Pathway: <strong className="text-gray-800">{selectedProgram.pathway_category}</strong>
            </p>
            <p className="text-gray-500 text-xs mt-2 max-w-2xl">
              <strong>Min. Entry Requirement:</strong> {selectedProgram.min_requirements_text}
            </p>
          </div>

          {/* Progress Tracker Card */}
          <div className="bg-white p-5 rounded-2xl border border-blue-100 shadow-sm w-full md:w-64 shrink-0">
            <div className="flex justify-between items-center text-xs font-bold mb-2">
              <span className="text-gray-500">Preparation Progress</span>
              <span className="text-blue-600">{progressPercent}%</span>
            </div>
            <div className="w-full bg-gray-100 h-2.5 rounded-full overflow-hidden mb-2">
              <div 
                className="bg-blue-600 h-full transition-all duration-300 rounded-full"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <p className="text-[11px] text-gray-400 text-center">
              {completedCount} of {totalItems} modules prepared
            </p>
          </div>
        </div>

        {/* ONLINE LEARNING SOURCES SECTION (preparatory_guideline) */}
        <div className="mb-12">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-xl font-extrabold text-gray-900 flex items-center gap-2">
                <span>📚 Recommended Online Learning Sources</span>
                <span className="text-xs bg-blue-100 text-blue-700 px-2.5 py-0.5 rounded-full font-bold">
                  {guidelines.length} Curated Courses
                </span>
              </h3>
              <p className="text-xs text-gray-500 mt-1">
                Authoritative online courses matched directly to your first-year curriculum requirements.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {guidelines.map((course, idx) => {
              const isDone = !!completedItems[idx];
              const badgeStyle = getPlatformStyle(course.platform);

              return (
                <div 
                  key={idx}
                  className={`bg-white rounded-3xl p-6 border-2 transition-all flex flex-col justify-between ${
                    isDone 
                      ? 'border-emerald-300 bg-emerald-50/20 shadow-sm'
                      : 'border-gray-100 hover:border-blue-200 shadow-sm hover:shadow-md'
                  }`}
                >
                  <div>
                    {/* Platform Badge & Subject */}
                    <div className="flex justify-between items-center mb-4 gap-2">
                      <span className={`text-xs font-extrabold px-3 py-1 rounded-full flex items-center gap-1.5 shrink-0 ${badgeStyle.bg}`}>
                        <span>{badgeStyle.icon}</span>
                        <span>{course.platform}</span>
                      </span>

                      <span className="text-xs text-gray-400 font-semibold text-right truncate">
                        {course.subject}
                      </span>
                    </div>

                    {/* Course Title */}
                    <h4 className="text-base font-bold text-gray-900 mb-2 leading-snug">
                      {course.title}
                    </h4>

                    <p className="text-xs text-gray-500 mb-6 leading-relaxed">
                      Recommended preparation module for foundational competencies in <strong>{course.subject}</strong>.
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="pt-4 border-t border-gray-100 flex items-center justify-between gap-3">
                    <button
                      onClick={() => toggleCheck(idx)}
                      className={`text-xs font-bold px-3.5 py-2 rounded-xl transition flex items-center gap-1.5 cursor-pointer ${
                        isDone 
                          ? 'bg-emerald-600 text-white' 
                          : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                      }`}
                    >
                      <span>{isDone ? '✓ Completed' : 'Mark Complete'}</span>
                    </button>

                    <a
                      href={course.link}
                      target="_blank"
                      rel="noreferrer"
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-xl shadow transition flex items-center gap-1"
                    >
                      <span>Open Course</span>
                      <span>↗</span>
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* KNOWLEDGE CONTEXT & SYLLABUS OVERVIEW */}
        <div className="bg-gray-50 rounded-3xl p-6 md:p-8 border border-gray-200/80 mb-10">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-8 h-8 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-sm">
              💡
            </span>
            <h3 className="text-lg font-bold text-gray-900">
              What You Will Learn in Semester 1 & 2
            </h3>
          </div>
          <p className="text-gray-700 text-xs md:text-sm leading-relaxed pl-11">
            {selectedProgram.knowledge_context}
          </p>
        </div>

        {/* ALTERNATIVE DIPLOMA PATHWAYS ADVISORY */}
        {selectedProgram.alternative_pathway_ids && selectedProgram.alternative_pathway_ids.length > 0 && (
          <div className="border-2 border-dashed border-blue-200 rounded-3xl p-6 mb-10 bg-blue-50/30">
            <h4 className="text-sm font-extrabold text-blue-900 mb-1 flex items-center gap-2">
              <span>🔄 Related / Alternative UniKL Pathways</span>
            </h4>
            <p className="text-xs text-gray-600 mb-3 leading-relaxed">
              Click any related pathway below to view its preparation plan and online courses:
            </p>
            <div className="flex flex-wrap gap-2">
              {selectedProgram.alternative_pathway_ids.map((altId, idx) => {
                const altProg = testplanData.find(p => p.program_id === altId);
                return (
                  <button
                    key={idx}
                    onClick={() => altProg && handleSelectProgram(altProg)}
                    className="bg-white hover:bg-blue-600 hover:text-white border border-blue-200 text-blue-800 text-xs font-bold px-3.5 py-2 rounded-xl shadow-sm transition cursor-pointer"
                  >
                    {altProg ? `${altProg.title} (${altProg.campuses})` : altId.replace(/_/g, ' ').toUpperCase()} →
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* BOTTOM ACTION BAR */}
        <div className="pt-6 border-t border-gray-100 flex flex-col sm:flex-row justify-between items-center gap-4">
          <button
            onClick={() => navigate('/recommendation')}
            className="w-full sm:w-auto px-6 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold text-xs rounded-2xl transition cursor-pointer"
          >
            ← Back to Recommendations
          </button>

          <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto justify-end">
            <button
              onClick={() => window.print()}
              className="px-5 py-3 border border-gray-300 hover:bg-gray-50 text-gray-700 font-bold text-xs rounded-2xl transition cursor-pointer flex items-center gap-1.5"
            >
              <span>🖨️</span>
              <span>Print / Save Plan</span>
            </button>
            <a
              href={selectedProgram.link}
              target="_blank"
              rel="noreferrer"
              className="px-6 py-3 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs rounded-2xl shadow-lg transition cursor-pointer flex items-center gap-1.5"
            >
              <span>Apply to UniKL</span>
              <span>↗</span>
            </a>
            <button
              onClick={() => navigate('/dashboard')}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-2xl shadow-lg transition cursor-pointer"
            >
              Finish & Return to Dashboard 🎉
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};

export default PreparationPlan;

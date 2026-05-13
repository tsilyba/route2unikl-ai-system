import React, { useState, useEffect } from 'react';
import { db } from '../../firebase';
import { collection, getDocs } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';

const AllPrograms = () => {
  const [programs, setPrograms] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedLevel, setSelectedLevel] = useState("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchPrograms = async () => {
      try {
        const querySnapshot = await getDocs(collection(db, 'programs'));
        const list = querySnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
        setPrograms(list);
        setLoading(false);
      } catch (err) {
        console.error("Error fetching programs:", err);
        setLoading(false);
      }
    };
    fetchPrograms();
  }, []);

  // Filter logic: Search by title or specialisation
 const filteredPrograms = programs.filter(program => {
  // Check Search Term
  const matchesSearch = 
    program.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    program.specialisation.toLowerCase().includes(searchTerm.toLowerCase());

  // Check Dropdown Level
  const matchesLevel = selectedLevel === "" || program.level === selectedLevel;

  return matchesSearch && matchesLevel;
});


  if (loading) return <div className="p-20 text-center font-bold text-blue-600 text-xl">Loading...</div>;

  return (
    <div className="bg-gray-50 min-h-screen pb-20">
      {/* Header Section */}
      <div className="bg-grey-600 py-16 px-4">
        <div className="max-w-6xl mx-auto text-center">
          <h1 className="text-4xl font-extrabold text-black mb-4">UniKL Programme</h1>
          <p className="text-black-100 text-lg mb-8">Discover your future at UniKL - Foundation and Diploma programmes.</p>
          
          {/* Search Bar */}
          <div className="max-w-xl mx-auto relative">
            <input 
              type="text"
              placeholder="Search by program name or specialization..."
              className="w-full p-4 rounded-2xl shadow-xl focus:outline-none focus:ring-4 focus:ring-blue-300 transition"
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            <span className="absolute right-5 top-4 text-2xl">🔍</span>
          </div>
        </div>
      </div>

      {/* Grid Section */}
      <div className="max-w-7xl mx-auto px-4 mt-12">
        <div className="flex justify-between items-center mb-8">
          <h2 className="text-2xl font-bold text-gray-800">{filteredPrograms.length} Programmes</h2>
        </div>

        {filteredPrograms.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-3xl border-2 border-dashed border-gray-200">
            <p className="text-gray-400 text-lg">No programmes match your search.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {filteredPrograms.map((program) => (
              <div key={program.id} className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all flex flex-col justify-between">
                <div>
                  <div className="flex justify-between items-start mb-4">
                    <span className={`text-xs font-bold uppercase tracking-wider ${program.level === 'Foundation' ? ' text-orange-600' : 'text-green-600'}`}>
                      {program.level}
                    </span>
                    <span className="text-xs font-medium text-gray-400">{program.campuses}</span>
                  </div>
                  <h3 className="text-xl font-bold text-gray-800 mb-3 leading-tight">{program.title}</h3>
                  <p className="text-gray-500 text-sm mb-6 leading-relaxed">{program.short_description}</p>
                  
                    <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">Specialisation</p>
                    <p className="text-sm font-semibold text-blue-700">{program.specialisation}</p>
                  
                </div>

                <a 
                  href={program.link} 
                  target="_blank" 
                  rel="noreferrer"
                  className="mt-8 w-full py-3 bg-blue-50 text-blue-600 text-center rounded-xl font-bold hover:bg-blue-600 hover:text-white transition-colors"
                >
                  View Details
                </a>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default AllPrograms;
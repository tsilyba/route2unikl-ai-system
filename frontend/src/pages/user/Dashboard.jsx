import React, { useState, useEffect } from 'react';
import { db } from '../../firebase';  // Import db from firebase.js
import { collection, getDocs } from 'firebase/firestore';  // Import necessary Firestore functions

const Dashboard = () => {
  const [programs, setPrograms] = useState([]);  // State to store the programs
  const [loading, setLoading] = useState(true);  // State to track loading status
  const [error, setError] = useState(null);  // State to store any errors

  useEffect(() => {
    // Fetch programs from Firestore when the component mounts
    const fetchPrograms = async () => {
      try {
        // Fetch data from the Firestore 'programs' collection
        const querySnapshot = await getDocs(collection(db, 'programs'));  // Get programs collection from Firestore
        const programsList = querySnapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data(),  // Spread the document data into the object
        }));

        setPrograms(programsList);  // Set the programs to the state
        setLoading(false);  // Set loading to false once data is fetched
      } catch (error) {
        console.error('Error fetching programs:', error);
        setError(error.message);  // Store the error message
        setLoading(false);  // Set loading to false in case of an error
      }
    };

    fetchPrograms();  // Call the fetch function
  }, []);  // Empty dependency array means this effect runs only once when the component mounts

  // Check if there is an error
  if (error) {
    return <div>Error: {error}</div>;
  }

  // Show a loading message while data is being fetched
  if (loading) {
    return <div>Loading programs...</div>;
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50 py-8">
      <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-5xl border border-gray-100">
        
        {/* Welcome Section */}
        <div className="text-center mb-8">
          <h2 className="text-3xl font-bold mb-6 text-blue-600">Hi! Ready to discover your best path? ✨</h2>
          <p className="text-gray-700 mb-4">Your journey to UniKL starts here. Let’s explore, plan, and achieve your dreams together!</p>
          <button className="bg-blue-600 text-white px-6 py-3 rounded-md hover:bg-blue-500 transition">
            Start Assessment
          </button>
        </div>

        {/* Programs Offered Section */}
        <div className="mb-8">
          <h3 className="text-2xl font-semibold text-blue-600 mb-4">Programs at UniKL</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
            {programs.length === 0 ? (
              <p>No programs available at the moment.</p>
            ) : (
              programs.map((program) => (
                <div key={program.id} className="p-6 bg-gray-100 rounded-lg shadow-md">
                  <h4 className="text-lg font-semibold text-blue-500">{program.title}</h4>
                  <p className="text-gray-600 mt-2">{program.short_description}</p>
                  <p className="text-gray-600 mt-2"><strong>Specialisation:</strong> {program.specialisation}</p>
                  <a href={program.link} className="text-blue-600 mt-4">Learn More</a>
                </div>
              ))
            )}
          </div>
        </div>

      </div>
    </div>
  );
};

export default Dashboard;
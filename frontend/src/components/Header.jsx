import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { auth } from '../firebase';

const Header = () => {
  const [user, setUser] = useState(null); // Track if user is logged in
  const navigate = useNavigate();

  // Listen for Auth changes
  useEffect(() => {
    const unsubscribe = auth.onAuthStateChanged((currentUser) => {
      setUser(currentUser);
    });
    return () => unsubscribe();
  }, []);

  const handleLogout = () => {
    const confirmLogout = window.confirm("Are you sure you want to log out?");
    
    if (confirmLogout) {
      auth.signOut().then(() => navigate('/'));
    }
  };

  return (
    <nav className="bg-white shadow-sm px-6 py-4 flex justify-between items-center">
      <Link to="/" className="text-xl font-bold text-blue-600">
        Route2UniKL
      </Link>
      
      <div className="flex items-center gap-6 items-center">
        {/* Links shown to EVERYONE */}
        <Link to="/all-programs" className="text-gray-600 hover:text-blue-600">Programs</Link>

        {/* 1. If USER is logged in, show these */}
        {user ? (
          <>
            <Link to="/profile" className="text-gray-600 hover:text-blue-600">Profile</Link>
            <button 
              onClick={handleLogout}
              className="ml-4 px-4 py-2 text-red-600 rounded-xl font-bold hover:text-red-700 transition cursor-pointer"
            >
              Logout
            </button>
          </>
        ) : (
          <>
            <Link 
              to="/login" 
              className="px-5 py-2 text-blue-600 rounded-xl font-bold hover:text-blue-700 transition"
            >
              Login
            </Link>
          </>
        )}
      </div>
    </nav>
  );
};

export default Header;
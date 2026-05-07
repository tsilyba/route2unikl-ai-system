import React from 'react';
import { Link } from 'react-router-dom';

const Header = () => {
  return (
    <nav className="bg-white shadow-sm px-6 py-4 flex justify-between items-center">
      <Link to="/dashboard" className="text-xl font-bold text-blue-600">
        Route2UniKL
      </Link>
      <div className="flex gap-6">
        <Link to="/dashboard" className="text-gray-600 hover:text-blue-600">Home</Link>
        <Link to="/all-programs" className="text-gray-600 hover:text-blue-600">Programs</Link>
        <Link to="/profile" className="text-gray-600 hover:text-blue-600">Profile</Link>
        
      </div>
    </nav>
  );
};

// VITE IS LOOKING FOR THIS EXACT LINE:
export default Header;
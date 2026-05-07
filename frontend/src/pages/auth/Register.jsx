//frontend/src/pages/auth/Register.jsx
import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { doc, setDoc } from 'firebase/firestore';
import { auth, db } from '../../firebase';

const Register = () => {
  //state variables!
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState(''); // New field added
  const [role, setRole] = useState('spm_leaver');
  const [error, setError] = useState('');
  
  const navigate = useNavigate();

  const handleRegister = async (e) => {
    e.preventDefault(); 
    setError(''); 


// basic validation to check if password and confirm password match
    if (password !== confirmPassword) {
      setError('Passwords do not match. Please try again.');
      return; 
    }

    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      const user = userCredential.user;

      await setDoc(doc(db, 'users', user.uid), {
        name: name,
        email: user.email,
        role: role,
        createdAt: new Date()
      });

      alert("Registration Successful! Please login.");
      navigate('/login');
      
    } catch (err) {
      console.error("Error during registration:", err);
      setError(err.message); 
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100">
        <h2 className="text-3xl font-bold mb-6 text-center text-blue-600">Join Route2MIIT</h2>
        
        {error && <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md text-sm">{error}</div>}

        <form onSubmit={handleRegister} className="space-y-5">
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
            <input 
              type="text" 
              required
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="e.g., Ali Bin Abu"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
            <input 
              type="email" 
              required
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input 
              type="password" 
              required
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="Minimum 6 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {/* Confirm Password Input Field */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
            <input 
              type="password" 
              required
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="Re-enter your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">I am a...</label>
            <select 
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              <option value="spm_leaver">SPM Leaver</option>
              <option value="form_4_5">Form 4 / Form 5 Student</option>
            </select>
          </div>

          <button 
            type="submit" 
            className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300"
          >
            Create Account
          </button>
        </form>
        
        <div className="mt-6 text-center text-gray-600">
          <p className="text-sm">
            Already have an account?{' '}
            <Link to="/login" className="text-blue-600 hover:underline font-semibold">
              Log in here
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Register;

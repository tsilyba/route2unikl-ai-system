//frontend/src/pages/auth/forgotpassword.jsx

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { sendPasswordResetEmail } from 'firebase/auth';
import { auth } from '../../firebase';

const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setMessage('');
    setError('');

    try {
      // This is the magic Firebase function
      await sendPasswordResetEmail(auth, email);
      setMessage('Password reset email sent! Check your inbox (and spam folder).');
    } catch (err) {
      console.error("Error resetting password:", err);
      // Make Firebase errors a bit more user-friendly
      if (err.code === 'auth/user-not-found') {
        setError("We couldn't find an account with that email.");
      } else {
        setError("Failed to send reset email. Please try again.");
      }
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100">
        <h2 className="text-3xl font-bold mb-2 text-center text-blue-600">Reset Password</h2>
        <p className="text-center text-gray-600 mb-6 text-sm">
          Enter your email address and we will send you a link to reset your password.
        </p>
        
        {/* Success Message Banner */}
        {message && <div className="mb-4 p-3 bg-green-100 text-green-700 rounded-md text-sm font-medium">{message}</div>}
        
        {/* Error Message Banner */}
        {error && <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md text-sm font-medium">{error}</div>}

        <form onSubmit={handleResetPassword} className="space-y-5">
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

          <button 
            type="submit" 
            className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300"
          >
            Send Reset Link
          </button>
        </form>
        
        <div className="mt-6 text-center text-gray-600">
          <p className="text-sm">
            Remembered your password?{' '}
            <Link to="/login" className="text-blue-600 hover:underline font-semibold">
              Log in here
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
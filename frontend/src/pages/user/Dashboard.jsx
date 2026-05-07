//frontend/pages/user/dashboard.jsx
import React from 'react';
import { auth } from '../../firebase';

const Dashboard = () => {
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100 text-center">
        <h2 className="text-3xl font-bold mb-6 text-blue-600">Welcome to Your Dashboard</h2>
        <p className="text-gray-700 mb-4">This is your personalized space where you can access all your information and manage your account.</p>
        <p className="text-gray-700 mb-4">Explore the features and make the most out of Route2MIIT!</p>         
      </div>
    </div>
  );
};

export default Dashboard;
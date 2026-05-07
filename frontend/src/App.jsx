// frontend/src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

// 1. Updated Auth Imports
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import ForgotPassword from './pages/auth/ForgotPassword';

// 2. Updated User Imports
import Dashboard from './pages/user/Dashboard';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        
        {/* Auth Routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        
        {/* User Routes */}
        <Route path="/dashboard" element={<Dashboard />} />
        
        <Route path="*" element={<h1 className="text-center mt-20 text-2xl font-bold text-gray-700">404 - Page Not Found</h1>} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

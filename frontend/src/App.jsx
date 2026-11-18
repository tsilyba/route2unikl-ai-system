// frontend/src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

// 1. Updated Auth Imports
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import ForgotPassword from './pages/auth/ForgotPassword';
import Layout from './components/Layout';
import AllPrograms from './pages/user/AllPrograms';
import Profile from './pages/user/Profile';
import Dashboard from './pages/user/dashboard';
import LandingPage from './pages/LandingPage';
import UploadResults from './pages/user/UploadResults';
import ManualGradeEntry from './pages/user/ManualGradeEntry';
import DummyAIAssessment from './pages/user/DummyAI';
import ProfileIngestion from './pages/user/ProfileIngestion';
import Recommendation from './pages/user/Recommendation';
import PreparationPlan from './pages/user/PreparationPlan';
import Stepper from './components/Stepper';
import { seedFoundationPrograms } from './assets/seedProgram';

function App() {
  return (
    <BrowserRouter>
      {/* Dev Seeding Button */}
      <button 
        onClick={seedFoundationPrograms} 
        className="fixed bottom-4 right-4 z-50 bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs px-4 py-2.5 rounded-full shadow-2xl transition-all cursor-pointer flex items-center gap-1.5"
      >
        <span>🌱</span> Seed Programs to Firestore
      </button>

      <Layout>
       <Routes>
        <Route path="/" element={<LandingPage />} />
        
        {/* Auth Routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        
        {/* User Routes */}
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/all-programs" element={<AllPrograms />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/profile-ingestion"element={<ProfileIngestion />} />
        <Route path="/upload-results" element={<UploadResults />} />
        <Route path="/manual-grade-entry" element={<ManualGradeEntry />} />
        <Route path="/ai-assessment" element={<DummyAIAssessment />} />
        <Route path="/recommendation" element={<Recommendation />} />
        <Route path="/preparation-plan" element={<PreparationPlan />} />

        {/* Catch-all for undefined routes */}
        
        <Route path="*" element={<h1 className="text-center mt-20 text-2xl font-bold text-gray-700">404 - Page Not Found</h1>} />
      </Routes>
      </Layout>

    </BrowserRouter>
  );
}

export default App;

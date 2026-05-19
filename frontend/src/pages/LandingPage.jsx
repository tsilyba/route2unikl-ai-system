import React, { useEffect } from 'react'; // Added useEffect
import { useNavigate } from 'react-router-dom';
import { auth } from '../firebase';
import { onAuthStateChanged } from 'firebase/auth';

const LandingPage = () => {
  const navigate = useNavigate();

  // 1. AUTO-REDIRECT LOGGED-IN USERS
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (user) {
        navigate('/dashboard');
      }
    });
    return () => unsubscribe();
  }, [navigate]);

  return (
    <div 
      className="min-h-screen bg-cover bg-center bg-no-repeat relative overflow-x-hidden"
      style={{ backgroundImage: "url('/background.png')" }} 
    >
      {/* 1. Hero Section */}
      <section className="pt-20 pb-32 px-6">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center gap-12">
          
          {/* Left Content */}
          <div className="flex-1 text-center md:text-left z-10">
            <h1 className="text-5xl md:text-7xl font-black text-[#1e293b] leading-[1.1] mb-8">
              Your Journey to <br />
              <span className="text-[#2563eb]">UniKL</span> Starts <br />
              With a Single Step.
            </h1>
            <p className="text-xl text-gray-600 mb-10 leading-relaxed max-w-lg font-medium">
              Use our AI-powered cognitive assessment to find the program that actually matches your strengths.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center md:justify-start">
              <button 
                onClick={() => navigate('/login')}
                className="px-10 py-4 bg-[#1d4ed8] text-white rounded-2xl font-bold text-lg shadow-2xl shadow-blue-200 hover:bg-blue-800 transition-all transform hover:-translate-y-1"
              >
                Click Here to Start
              </button>
              <button 
                onClick={() => navigate('/all-programs')}
                className="px-10 py-4 bg-white text-[#1d4ed8] border-2 border-gray-100 rounded-2xl font-bold text-lg hover:bg-gray-50 transition-all"
              >
                Browse Programs
              </button>
            </div>
          </div>

          {/* Right Content (The Mascot) */}
          <div className="flex-1 flex justify-center items-center relative">
            {/* Soft glow behind the robot */}
            <div className="absolute w-64 h-64 bg-blue-400/20 rounded-full blur-3xl animate-pulse"></div>
            
            <img 
              src="/mascot.png" 
              alt="UniKL Robot Guide" 
              className="w-full max-w-[480px] h-auto drop-shadow-2xl animate-float"
            />
          </div>
        </div>
      </section>

      {/* 2. Feature Section */}
      <section className="py-24 bg-white/60 backdrop-blur-md px-6 border-t border-white/20">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">How Route2UniKL Works</h2>
            <div className="h-1.5 w-16 bg-blue-600 mx-auto rounded-full"></div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
            {[
              { step: '01', title: 'Cognitive Quiz', desc: 'Take a short, smart assessment based on RIASEC standards.' },
              { step: '02', title: 'Smart Matching', desc: 'Receive a list of UniKL programs that perfectly align with your profile.' },
              { step: '03', title: 'Early Prep', desc: 'Get Ready with Personalized Study Plans' }
            ].map((item, idx) => (
              <div key={idx} className="bg-white/80 p-8 rounded-3xl shadow-sm border border-white hover:shadow-md transition">
                <span className="text-4xl font-black text-blue-100 mb-4 block">{item.step}</span>
                <h3 className="text-xl font-bold text-gray-800 mb-2">{item.title}</h3>
                <p className="text-gray-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 3. CTA Section */}
      <section className="py-20 px-6 text-center">
        <div className="max-w-4xl mx-auto bg-blue-600 rounded-[3rem] p-12 shadow-2xl shadow-blue-200">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">Ready to find your programmes?</h2>
          <button 
            onClick={() => navigate('/login')}
            className="bg-white text-blue-600 px-10 py-4 rounded-2xl font-bold text-lg hover:bg-blue-50 transition-all shadow-lg"
          >
            Sign Up Route2UniKL
          </button>
        </div>
      </section>

      {/* 4. MISSING FLOATING ANIMATION STYLE */}
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes float {
          0% { transform: translateY(0px); }
          50% { transform: translateY(-20px); }
          100% { transform: translateY(0px); }
        }
        .animate-float {
          animation: float 4s ease-in-out infinite;
        }
      `}} />
    </div>
  );
};

export default LandingPage;
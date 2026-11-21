// frontend/src/pages/auth/Login.jsx
import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { signInWithEmailAndPassword, signOut } from 'firebase/auth';
import { auth } from '../../firebase';
import { hasAdminClaim, ADMIN_HOME, STUDENT_HOME } from '../../utils/adminClaims';

// Reads the `admin` claim from a freshly issued ID token, retrying once so a
// momentary network blip does not fail the login. Throws if both attempts fail.
const CLAIM_CHECK_ATTEMPTS = 2;
const verifyAdminClaim = async (user) => {
  let lastError;
  for (let attempt = 1; attempt <= CLAIM_CHECK_ATTEMPTS; attempt++) {
    try {
      return await hasAdminClaim(user, { forceRefresh: true });
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
};

// Map Firebase Auth error codes to user-friendly messages.
// Credential errors share one message so the form does not reveal which emails are registered.
const getLoginErrorMessage = (code) => {
  switch (code) {
    case 'auth/invalid-credential':
    case 'auth/invalid-email':
    case 'auth/wrong-password':
    case 'auth/user-not-found':
      return 'Invalid email or password. Please try again.';
    case 'auth/user-disabled':
      return 'This account has been disabled. Please contact the Route2UniKL administrator.';
    case 'auth/too-many-requests':
      return 'Too many failed login attempts. Please wait a few minutes or reset your password.';
    case 'auth/network-request-failed':
      return 'Network error. Please check your internet connection and try again.';
    default:
      return 'Login failed. Please try again.';
  }
};

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const submittingRef = useRef(false); // blocks double submits before re-render

  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    if (submittingRef.current) return;
    submittingRef.current = true;
    setLoading(true);
    setError('');

    let user;
    try {
      ({ user } = await signInWithEmailAndPassword(auth, email, password));
    } catch (err) {
      console.error('Login failed:', err?.code || 'unknown error');
      setError(getLoginErrorMessage(err?.code));
      submittingRef.current = false;
      setLoading(false);
      return;
    }

    // Role-based redirect. Admin access comes ONLY from the server-assigned
    // `admin: true` custom claim — never from email or the Firestore `role` field.
    // If the claim cannot be read, do NOT guess a destination: "unknown" must
    // never be treated as "student", or a real admin is silently misrouted.
    let isAdmin;
    try {
      isAdmin = await verifyAdminClaim(user);
    } catch (err) {
      console.error('Could not verify account permissions:', err?.code || 'unknown error');
      await signOut(auth).catch(() => {});
      setError("You signed in, but we couldn't verify your account permissions. Please check your connection and try again.");
      submittingRef.current = false;
      setLoading(false);
      return;
    }

    const destination = isAdmin ? ADMIN_HOME : STUDENT_HOME;

    alert("Login Successful! Welcome back.");
    navigate(destination, { replace: true });
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100">
        <h2 className="text-3xl font-bold mb-6 text-center text-blue-600">Login</h2>

        {/* Display an error banner if login fails */}
        {error && <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md text-sm" role="alert">{error}</div>}

        <form onSubmit={handleLogin} className="space-y-5">
          {/* Email Input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
            <input
              type="email"
              required
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="example@gmail.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          {/* Password Input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              required
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {/* Forgot Password Link */}
          <div className="flex justify-end">
            <Link to="/forgot-password" className="text-sm text-blue-600 hover:underline">
              Forgot password?
            </Link>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? 'Logging in...' : 'Log In'}
          </button>
        </form>

        <div className="mt-6 text-center text-gray-600">
          <p className="text-sm">
            Don't have an account?{' '}
            <Link to="/register" className="text-blue-600 hover:underline font-semibold">
              Register here
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;

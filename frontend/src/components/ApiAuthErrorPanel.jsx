// frontend/src/components/ApiAuthErrorPanel.jsx
//
// Shown when the backend rejects a request (HTTP 401/403) or when sign-in
// cannot be verified right now (HTTP 503 with code AUTH_SERVICE_UNAVAILABLE).
// Deliberately replaces the page content: authentication errors must never
// be hidden behind fallback questions or client-side recommendations.
import { useNavigate } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase';
import { AUTH_SERVICE_UNAVAILABLE } from '../utils/apiClient';

const VARIANTS = {
  serviceUnavailable: {
    title: 'Sign-in service temporarily unavailable',
    text: "We couldn't verify your sign-in right now, so this step was not loaded. Please try again in a moment.",
    action: 'retry',
    buttonLabel: 'Try again',
  },
  sessionProblem: {
    title: 'Please sign in again',
    text: 'Your session could not be verified, so we could not load this step.',
    action: 'login',
    buttonLabel: 'Log in again',
  },
  accessDenied: {
    title: 'Access denied',
    text: 'Your account is not allowed to access this information.',
    action: 'login',
    buttonLabel: 'Log in again',
  },
};

const getVariant = (error) => {
  // Classify by the machine-readable code first, then by HTTP status.
  if (error?.code === AUTH_SERVICE_UNAVAILABLE) return VARIANTS.serviceUnavailable;
  if (error?.status === 401) return VARIANTS.sessionProblem;
  return VARIANTS.accessDenied;
};

const ApiAuthErrorPanel = ({ error }) => {
  const navigate = useNavigate();
  const variant = getVariant(error);

  const handleAction = async () => {
    if (variant.action === 'retry') {
      // Temporary outage: keep the session and simply reload this step.
      window.location.reload();
      return;
    }
    await signOut(auth).catch(() => {});
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100 text-center" role="alert">
        <h2 className="text-2xl font-bold mb-3 text-blue-600">{variant.title}</h2>
        <p className="text-gray-600 text-sm mb-2">{variant.text}</p>
        {error?.message && (
          <p className="text-gray-400 text-xs mb-6">Details: {error.message}</p>
        )}
        <button
          type="button"
          onClick={handleAction}
          className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300 cursor-pointer"
        >
          {variant.buttonLabel}
        </button>
      </div>
    </div>
  );
};

export default ApiAuthErrorPanel;

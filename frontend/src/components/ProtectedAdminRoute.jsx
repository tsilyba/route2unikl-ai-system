// frontend/src/components/ProtectedAdminRoute.jsx
//
// Guards admin-only routes in the React app using the Firebase custom claim
// `admin: true`. This is a UX/navigation guard only: it does NOT secure any
// data. Firestore Security Rules and FastAPI endpoints must enforce the same
// claim server-side, because anyone can bypass client-side JavaScript.
//
// Usage (either form):
//   <Route path="/admin/dashboard" element={<ProtectedAdminRoute><Page /></ProtectedAdminRoute>} />
//   <Route path="/admin" element={<ProtectedAdminRoute />}> ...nested admin routes... </Route>
import { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, Outlet } from 'react-router-dom';
import { onAuthStateChanged, signOut } from 'firebase/auth';
import { auth } from '../firebase';
import { hasAdminClaim, STUDENT_HOME } from '../utils/adminClaims';
import { SIGN_OUT_FAILED_MESSAGE, createAttemptTracker, endSession } from '../utils/signOutFlow';

// Firebase error codes meaning the stored session is no longer valid.
const SESSION_ENDED_CODES = new Set([
  'auth/user-token-expired',
  'auth/user-disabled',
  'auth/user-not-found',
  'auth/invalid-user-token',
]);

const ProtectedAdminRoute = ({ children }) => {
  // 'checking' | 'admin' | 'not-admin' | 'signed-out' | 'error' | 'signing-out' | 'sign-out-failed'
  const [status, setStatus] = useState('checking');
  const [attempt, setAttempt] = useState(0);
  const [signOutAttempts] = useState(createAttemptTracker);

  // Ends an invalid session. 'signed-out' (redirect to /login) is set ONLY after
  // sign-out succeeds; a failure shows a blocked screen with a retry. Admin content
  // is never rendered meanwhile. Superseded attempts and unmounts are ignored.
  const endInvalidSession = useCallback(
    (isCurrent = () => true) => {
      const isLatest = signOutAttempts.begin();
      return endSession({
        signOut: () => signOut(auth),
        onSignedOut: () => setStatus('signed-out'),
        onFailed: () => setStatus('sign-out-failed'),
        isActive: () => isLatest() && isCurrent(),
      });
    },
    [signOutAttempts]
  );

  // Pending sign-out callbacks are ignored once the guard unmounts.
  useEffect(() => () => signOutAttempts.cancel(), [signOutAttempts]);

  useEffect(() => {
    let active = true;

    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (!active) return;

      if (!user) {
        setStatus('signed-out');
        return;
      }

      // Deny by default while the claim is being (re)verified.
      setStatus('checking');

      // Ignore stale results if the user signed out or switched accounts
      // while the token request was in flight.
      const isStillCurrent = () => active && auth.currentUser?.uid === user.uid;

      try {
        // Force-refresh so a recently granted or revoked claim is honoured.
        const isAdmin = await hasAdminClaim(user, { forceRefresh: true });
        if (isStillCurrent()) setStatus(isAdmin ? 'admin' : 'not-admin');
      } catch (err) {
        if (!isStillCurrent()) return;
        console.error('Admin access check failed:', err?.code || 'unknown error');

        if (SESSION_ENDED_CODES.has(err?.code)) {
          // Session is invalid: end it, then send the user to log in. The status
          // stays 'checking' (no admin content) until sign-out has finished.
          endInvalidSession(() => active);
        } else {
          // e.g. network failure: never grant access, offer a retry instead.
          setStatus('error');
        }
      }
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [attempt, endInvalidSession]);

  const handleRetry = () => {
    setStatus('checking');
    setAttempt((n) => n + 1);
  };

  const retrySignOut = () => {
    setStatus('signing-out');
    endInvalidSession();
  };

  if (status === 'checking' || status === 'signing-out') {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-slate-50 px-4 text-center text-xl font-bold text-blue-600"
        role="status"
        aria-live="polite"
      >
        {status === 'signing-out' ? 'Signing out...' : 'Verifying admin access...'}
      </div>
    );
  }

  if (status === 'signed-out') {
    return <Navigate to="/login" replace />;
  }

  if (status === 'not-admin') {
    return <Navigate to={STUDENT_HOME} replace />;
  }

  // Sign-out of an invalid session failed: stay here (no admin content, no redirect).
  if (status === 'sign-out-failed') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 px-4">
        <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100 text-center" role="alert">
          <h2 className="text-2xl font-bold mb-3 text-blue-600">Couldn't sign you out</h2>
          <p className="text-gray-600 text-sm mb-6">Your session has ended. {SIGN_OUT_FAILED_MESSAGE}</p>
          <button
            type="button"
            onClick={retrySignOut}
            className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300 cursor-pointer"
          >
            Try signing out again
          </button>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 px-4">
        <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100 text-center" role="alert">
          <h2 className="text-2xl font-bold mb-3 text-blue-600">Unable to verify access</h2>
          <p className="text-gray-600 text-sm mb-6">
            We couldn't confirm your admin permissions. Please check your internet connection and try again.
          </p>
          <button
            type="button"
            onClick={handleRetry}
            className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300 cursor-pointer"
          >
            Try Again
          </button>
          <Link to="/login" className="block mt-4 text-sm text-blue-600 hover:underline font-semibold">
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  // status === 'admin'
  return children ?? <Outlet />;
};

export default ProtectedAdminRoute;

// frontend/src/components/admin/AdminLayout.jsx
//
// Layout for every /admin/* page. Rendered only after ProtectedAdminRoute has
// confirmed the Firebase custom claim `admin: true` in the browser. It then
// asks the server to confirm Admin access (GET /api/admin/verify, protected by
// require_admin) and renders NO admin content until that succeeds.
//
// Frontend checks only control what is displayed. Data protection comes from
// FastAPI's require_admin on every Admin endpoint and from firestore.rules.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { auth } from '../../firebase';
import { authFetch } from '../../utils/apiClient';
import { VERIFY_STATUS, verifyAdminAccess } from '../../utils/adminVerification';
import { createAttemptTracker, endSession } from '../../utils/signOutFlow';
import { ADMIN_DASHBOARD_PATH, getAdminPageTitle } from './adminNavigation';
import AdminHeader from './AdminHeader';
import AdminIcon from './AdminIcons';
import AdminSidebar from './AdminSidebar';
import AdminStatusPanel from './AdminStatusPanel';

const SIGNING_OUT = 'signing-out';
const SIGN_OUT_FAILED = 'sign-out-failed';
const DESKTOP_QUERY = '(min-width: 1024px)';

const AdminLayout = () => {
  // { status, verifiedAt?, email? } — admin content renders only for VERIFIED.
  const [verification, setVerification] = useState({ status: VERIFY_STATUS.CHECKING });
  const [attempt, setAttempt] = useState(0);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [signOutAttempts] = useState(createAttemptTracker);
  const menuButtonRef = useRef(null);
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // Automatic sign-out of an expired session (HTTP 401). Admin content stays hidden
  // throughout: "Session expired" while signing out, then the login page ONLY after
  // sign-out succeeds; on failure, "Couldn't sign you out" with a retry button.
  // Superseded attempts, stale verifications and unmounted layouts are ignored.
  const endExpiredSession = useCallback(
    (isCurrent = () => true) => {
      const isLatest = signOutAttempts.begin();
      setVerification({ status: VERIFY_STATUS.SESSION_EXPIRED });
      return endSession({
        signOut: () => signOut(auth),
        onSignedOut: () => navigate('/login', { replace: true }),
        onFailed: () => setVerification({ status: SIGN_OUT_FAILED }),
        isActive: () => isLatest() && isCurrent(),
      });
    },
    [navigate, signOutAttempts]
  );

  // Pending sign-out callbacks are ignored once the layout unmounts.
  useEffect(() => () => signOutAttempts.cancel(), [signOutAttempts]);

  // Server-side Admin verification. Runs on mount and on every retry.
  // Late or stale results are ignored after unmount (including React StrictMode's
  // extra mount/unmount), after sign-out, or if the signed-in account changed.
  useEffect(() => {
    let active = true;
    const expectedUid = auth.currentUser?.uid ?? null;
    const isCurrent = () => active && (auth.currentUser?.uid ?? null) === expectedUid;

    verifyAdminAccess((path) => authFetch(path), { expectedUid })
      .catch(() => ({ status: VERIFY_STATUS.ERROR }))
      .then((result) => {
        if (!isCurrent()) return;

        if (result.status === VERIFY_STATUS.SESSION_EXPIRED) {
          endExpiredSession(() => active);
          return;
        }

        setVerification(
          result.status === VERIFY_STATUS.VERIFIED
            ? { ...result, email: auth.currentUser?.email ?? null }
            : { status: result.status }
        );
      });

    return () => {
      active = false;
    };
  }, [attempt, endExpiredSession]);

  const handleRetry = () => {
    setVerification({ status: VERIFY_STATUS.CHECKING });
    setAttempt((n) => n + 1);
  };

  // Ends the Firebase session and clears the Admin UI immediately.
  const performSignOut = async () => {
    setMobileNavOpen(false);
    setVerification({ status: SIGNING_OUT });
    try {
      await signOut(auth);
      navigate('/login', { replace: true });
    } catch (error) {
      console.error('Sign-out failed:', error?.code || 'unknown error');
      alert("We couldn't log you out. Please try again.");
      handleRetry();
    }
  };

  const handleLogout = () => {
    if (window.confirm('Are you sure you want to log out?')) {
      performSignOut();
    }
  };

  const closeMobileNav = useCallback(() => {
    setMobileNavOpen(false);
    menuButtonRef.current?.focus();
  }, []);

  // While the mobile menu is open: Escape closes it, the page behind does not
  // scroll, and it closes automatically if the window grows to desktop width.
  useEffect(() => {
    if (!mobileNavOpen) return undefined;

    const onKeyDown = (event) => {
      if (event.key === 'Escape') closeMobileNav();
    };
    const desktop = window.matchMedia(DESKTOP_QUERY);
    const onViewportChange = (event) => {
      if (event.matches) setMobileNavOpen(false);
    };
    const previousOverflow = document.body.style.overflow;

    document.addEventListener('keydown', onKeyDown);
    desktop.addEventListener('change', onViewportChange);
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      desktop.removeEventListener('change', onViewportChange);
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileNavOpen, closeMobileNav]);

  if (verification.status !== VERIFY_STATUS.VERIFIED) {
    // After a failed automatic sign-out, the panel's button retries that sign-out.
    const onSignOut = verification.status === SIGN_OUT_FAILED ? () => endExpiredSession() : performSignOut;
    return <AdminStatusPanel status={verification.status} onRetry={handleRetry} onSignOut={onSignOut} />;
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <AdminSidebar variant="desktop" onLogout={handleLogout} />

      {mobileNavOpen && (
        <>
          <div className="fixed inset-0 z-40 bg-slate-900/60 lg:hidden" aria-hidden="true" onClick={closeMobileNav} />
          <AdminSidebar
            variant="mobile"
            onLogout={handleLogout}
            onNavigate={() => setMobileNavOpen(false)}
            onClose={closeMobileNav}
          />
        </>
      )}

      <div className="flex min-h-screen min-w-0 flex-col lg:pl-64">
        <AdminHeader
          title={getAdminPageTitle(pathname)}
          email={verification.email}
          mobileNavOpen={mobileNavOpen}
          onMenuClick={() => setMobileNavOpen(true)}
          menuButtonRef={menuButtonRef}
          onLogout={handleLogout}
        />
        <main className="flex-1 overflow-x-hidden px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-6xl">
            <Outlet context={{ verification }} />
          </div>
        </main>
      </div>
    </div>
  );
};

// Shown for any /admin/* path without an implemented page (e.g. /admin/users).
export const AdminNotFound = () => (
  <section className="mx-auto mt-6 max-w-lg rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
    <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
      <AdminIcon name="alert" className="h-6 w-6" />
    </div>
    <h2 className="mb-2 text-xl font-bold text-slate-900">Page not found</h2>
    <p className="mb-6 text-sm text-slate-600">
      This admin page does not exist or is not available yet. Management modules are added in later milestones.
    </p>
    <Link
      to={ADMIN_DASHBOARD_PATH}
      className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
    >
      <AdminIcon name="arrowLeft" className="h-4 w-4" />
      Back to Dashboard
    </Link>
  </section>
);

export default AdminLayout;

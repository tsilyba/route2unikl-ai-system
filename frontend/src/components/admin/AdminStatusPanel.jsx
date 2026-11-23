// frontend/src/components/admin/AdminStatusPanel.jsx
//
// Full-screen states shown INSTEAD of the Admin area while server-side Admin
// verification is pending or has not succeeded. Admin content is never rendered
// behind these panels.
import { SIGN_OUT_FAILED_MESSAGE } from '../../utils/signOutFlow';
import AdminIcon from './AdminIcons';

const PANELS = {
  checking: {
    icon: 'shield',
    tone: 'info',
    title: 'Verifying admin access',
    text: 'Confirming your administrator access with the Route2UniKL server…',
    busy: true,
  },
  'signing-out': {
    icon: 'logout',
    tone: 'info',
    title: 'Signing out',
    text: 'Ending your admin session…',
    busy: true,
  },
  'session-expired': {
    icon: 'lock',
    tone: 'warning',
    title: 'Session expired',
    text: 'Your session is no longer valid. Signing you out…',
    busy: true,
  },
  // Automatic sign-out failed: the admin area stays blocked and nothing redirects.
  'sign-out-failed': {
    icon: 'lock',
    tone: 'danger',
    title: "Couldn't sign you out",
    text: `Your session is no longer valid. ${SIGN_OUT_FAILED_MESSAGE}`,
    signOut: true,
    signOutLabel: 'Try signing out again',
  },
  forbidden: {
    icon: 'lock',
    tone: 'danger',
    title: 'Admin access not confirmed',
    text: 'The Route2UniKL server did not confirm administrator access for this account, so the admin area is not available.',
    signOut: true,
  },
  'auth-unavailable': {
    icon: 'alert',
    tone: 'warning',
    title: 'Sign-in service temporarily unavailable',
    text: "We couldn't verify your sign-in right now. Please try again in a moment.",
    retry: true,
    signOut: true,
  },
  'server-unreachable': {
    icon: 'server',
    tone: 'warning',
    title: "Can't reach the Route2UniKL server",
    text: 'The admin area needs the Route2UniKL backend to confirm your access. Check that the server is running, then try again.',
    retry: true,
    signOut: true,
  },
  error: {
    icon: 'alert',
    tone: 'danger',
    title: 'Something went wrong',
    text: "We couldn't confirm your admin access. Please try again.",
    retry: true,
    signOut: true,
  },
};

const TONES = {
  info: 'bg-blue-50 text-blue-600',
  warning: 'bg-amber-50 text-amber-600',
  danger: 'bg-red-50 text-red-600',
};

const AdminStatusPanel = ({ status, onRetry, onSignOut }) => {
  const panel = PANELS[status] ?? PANELS.error;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-lg"
        role={panel.busy ? 'status' : 'alert'}
        aria-live={panel.busy ? 'polite' : 'assertive'}
      >
        <div className={`mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl ${TONES[panel.tone]}`}>
          <AdminIcon name={panel.icon} className="h-7 w-7" />
        </div>
        <h1 className="mb-2 text-xl font-bold text-slate-900">{panel.title}</h1>
        <p className="text-sm text-slate-600">{panel.text}</p>

        {panel.busy && (
          <div className="mx-auto mt-6 h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" aria-hidden="true" />
        )}

        {(panel.retry || panel.signOut) && (
          <div className="mt-6 flex flex-col gap-3">
            {panel.retry && (
              <button
                type="button"
                onClick={onRetry}
                className="w-full rounded-lg bg-blue-600 py-3 font-bold text-white transition hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 cursor-pointer"
              >
                Try again
              </button>
            )}
            {panel.signOut && (
              <button
                type="button"
                onClick={onSignOut}
                className="w-full rounded-lg border border-slate-300 py-3 font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 cursor-pointer"
              >
                {panel.signOutLabel ?? 'Sign out'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminStatusPanel;

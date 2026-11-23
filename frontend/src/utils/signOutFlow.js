// frontend/src/utils/signOutFlow.js
//
// Shared sign-out handling for the Admin area: AdminLayout and ProtectedAdminRoute
// (automatic sign-out of an ended session) and the Manage Users pages (M3A).
// Plain JavaScript with no Firebase or React imports, so it can be tested with:
//   node --test src/utils/signOutFlow.test.js
//
// Rules:
//   - Navigation, or any "signed out" state, happens ONLY after sign-out succeeds.
//     A failed sign-out never redirects; the caller shows an error and a retry.
//   - Overlapping requests share one sign-out attempt. Every caller signs out the
//     same Firebase Auth instance, so a caller that joins gets the same outcome.
//   - Callbacks of an unmounted component or of a superseded attempt are ignored.

export const SIGN_OUT_FAILED_MESSAGE =
  "We couldn't sign you out. Check your internet connection, then try again.";

let inFlight = null;

// Runs `signOut`, or joins the attempt already in progress. Rejects if it fails
// (including an immediate throw). Once settled, the next call starts a new attempt.
const runSignOut = (signOut) => {
  if (!inFlight) {
    inFlight = Promise.resolve()
      .then(() => signOut())
      .finally(() => {
        inFlight = null;
      });
  }
  return inFlight;
};

// Signs out, then opens the login page. Navigates ONLY after sign-out succeeds; on
// failure it rejects without navigating, so the caller can show an error and a retry.
// (Introduced in M3A; also re-exported from adminUsers.js.)
export const signOutThenRedirect = async (signOut, navigate) => {
  await runSignOut(signOut);
  navigate('/login', { replace: true });
};

// Sign-out for components that may unmount, re-verify or retry meanwhile.
// `onSignedOut` runs only after success and `onFailed` only after failure, each only
// if `isActive()` is still true when sign-out settles. Never rejects because of a
// sign-out failure. Resolves true if sign-out succeeded. Callbacks must not throw.
export const endSession = async ({ signOut, onSignedOut, onFailed, isActive = () => true }) => {
  try {
    await runSignOut(signOut);
  } catch {
    if (isActive()) onFailed();
    return false;
  }
  if (isActive()) onSignedOut();
  return true;
};

// Tracks a component's latest sign-out attempt. begin() returns an `isLatest`
// check that stays true until the next begin() or cancel(), so a superseded
// attempt (e.g. after a retry) or an unmounted component never runs its callbacks.
export const createAttemptTracker = () => {
  let latest = 0;
  return {
    begin() {
      latest += 1;
      const attempt = latest;
      return () => attempt === latest;
    },
    cancel() {
      latest += 1;
    },
  };
};

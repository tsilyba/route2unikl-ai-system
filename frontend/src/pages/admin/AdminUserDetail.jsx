// frontend/src/pages/admin/AdminUserDetail.jsx
//
// Admin "User Details" (Milestone M3A), with the Disable / Enable account actions (M3B-2).
// Account data comes from GET /api/admin/users/{uid} (require_admin). Academic records are
// shown as metadata only: grades and assessment answers are never requested or shown.
// The "Account access" panel uses GET /api/admin/users/{uid}/access and POST .../disable and
// .../enable (require_admin; available only when the backend runs with the local Firebase
// emulators). The browser never changes Firebase accounts itself.
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import AdminIcon from '../../components/admin/AdminIcons';
import ConfirmDialog from '../../components/admin/ConfirmDialog';
import { ADMIN_USERS_PATH } from '../../components/admin/adminNavigation';
import { disableAccount, enableAccount, fetchAccountAccess, fetchAdminUser } from '../../utils/adminUsersApi';
import {
  AdminUsersRequestError,
  formatDateTime,
  formatYesNo,
  getJourneyStepLabel,
  getProviderLabel,
  getStudentTypeLabel,
  isValidUid,
} from '../../utils/adminUsers';
import {
  describeAccessLoadError,
  describeAccountAccess,
  describeActionError,
  describeActionSuccess,
  getActionButtons,
  getConfirmation,
} from '../../utils/adminAccountActions';
import { AccountBadges, RequestErrorPanel } from './AdminUsers';

const NOT_FOUND = new AdminUsersRequestError(404, 'USER_NOT_FOUND');

const STATE_BADGE_TONES = {
  active: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  disabled: 'bg-red-50 text-red-700 ring-red-200',
  warning: 'bg-amber-50 text-amber-800 ring-amber-200',
  info: 'bg-blue-50 text-blue-700 ring-blue-200',
  admin: 'bg-blue-50 text-blue-700 ring-blue-200',
  neutral: 'bg-slate-100 text-slate-700 ring-slate-200',
};

const FEEDBACK_TONES = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  info: 'border-blue-200 bg-blue-50 text-blue-900',
  error: 'border-red-200 bg-red-50 text-red-900',
};

const ACTION_BUTTON_TONES = {
  danger: 'border border-red-300 bg-white text-red-700 hover:bg-red-50 focus-visible:outline-red-600',
  primary: 'bg-blue-600 text-white hover:bg-blue-700 focus-visible:outline-blue-600',
};

const secondaryButton =
  'rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 cursor-pointer';

// Disable / Enable (M3B-2). The server decides which actions are allowed; this panel shows its answer,
// asks for confirmation, prevents double submission and reports the outcome truthfully.
const AccountAccessPanel = ({ uid, name, refreshKey, onChanged }) => {
  const [reload, setReload] = useState(0);
  const loadKey = `${uid}#${refreshKey}#${reload}`;
  const [loaded, setLoaded] = useState({ key: null, uid: null, data: null, error: null });
  const [confirming, setConfirming] = useState(null); // the button whose action awaits confirmation
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const submittingRef = useRef(false);

  useEffect(() => {
    let active = true;
    fetchAccountAccess(uid)
      .then((data) => {
        if (active) setLoaded({ key: loadKey, uid, data, error: null });
      })
      .catch((error) => {
        // An expired session is handled by the page's own request (RequestErrorPanel).
        if (active) setLoaded({ key: loadKey, uid, data: null, error });
      });
    return () => {
      active = false;
    };
  }, [loadKey, uid]);

  const loading = loaded.key !== loadKey;
  const access = loaded.uid === uid ? loaded.data : null;

  const runAction = async () => {
    if (!confirming || submittingRef.current) return;
    submittingRef.current = true;
    const { action } = confirming;
    setPending(true);
    setFeedback(null);
    try {
      const result = await (action === 'disable' ? disableAccount : enableAccount)(uid);
      setLoaded({ key: loadKey, uid, data: result.account ?? null, error: null });
      setFeedback(describeActionSuccess(result));
      onChanged(); // refresh the account details shown on the page
    } catch (error) {
      setFeedback(describeActionError(error));
      setReload((n) => n + 1); // show the account's current state, for example an incomplete change
    } finally {
      submittingRef.current = false;
      setPending(false);
      setConfirming(null);
    }
  };

  let content;
  if (!access && loading) {
    content = (
      <p role="status" className="flex items-center gap-3 text-sm text-slate-600">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" aria-hidden="true" />
        Checking account access…
      </p>
    );
  } else if (!access) {
    const info = describeAccessLoadError(loaded.error);
    content = (
      <div className="space-y-3">
        <p className={`text-sm ${info.kind === 'unavailable' ? 'text-slate-600' : 'text-red-700'}`}>{info.message}</p>
        {info.retry && (
          <button type="button" onClick={() => setReload((n) => n + 1)} className={secondaryButton}>
            Try again
          </button>
        )}
      </div>
    );
  } else {
    const view = describeAccountAccess(access);
    const buttons = getActionButtons(access);
    content = (
      <div className="space-y-4" aria-busy={loading}>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${STATE_BADGE_TONES[view.tone] ?? STATE_BADGE_TONES.neutral}`}>
            {view.label}
          </span>
          {loading && <span className="text-xs font-medium text-blue-700">Updating…</span>}
        </div>
        <p className="text-sm text-slate-700">{view.description}</p>
        {view.details.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
            {view.details.map((detail) => <li key={detail}>{detail}</li>)}
          </ul>
        )}
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          {buttons.map((button) => (
            <button
              key={button.action}
              type="button"
              onClick={() => setConfirming(button)}
              disabled={pending || loading}
              className={`rounded-lg px-4 py-2 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 cursor-pointer ${ACTION_BUTTON_TONES[button.tone]}`}
            >
              {button.label}
            </button>
          ))}
          <button type="button" onClick={() => setReload((n) => n + 1)} disabled={pending || loading} className={secondaryButton}>
            Refresh
          </button>
        </div>
        <p className="text-xs text-slate-500">
          Changes go through protected server endpoints and are recorded in an audit log.
        </p>
      </div>
    );
  }

  const confirmation = confirming ? getConfirmation(confirming.action, { name, resume: confirming.resume }) : null;

  return (
    <section aria-labelledby="account-access-title" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 id="account-access-title" className="mb-4 flex items-center gap-2 text-base font-bold text-slate-900">
        <AdminIcon name="shield" className="h-5 w-5 text-slate-500" />
        Account access
      </h2>
      {feedback && (
        <div role={feedback.tone === 'error' ? 'alert' : 'status'} className={`mb-4 rounded-xl border p-3 text-sm ${FEEDBACK_TONES[feedback.tone] ?? FEEDBACK_TONES.info}`}>
          <p className="font-semibold">{feedback.title}</p>
          <p className="mt-1">{feedback.message}</p>
        </div>
      )}
      {content}
      {confirmation && (
        <ConfirmDialog
          title={confirmation.title}
          message={confirmation.message}
          confirmLabel={confirmation.confirmLabel}
          pendingLabel={confirmation.pendingLabel}
          tone={confirmation.tone}
          pending={pending}
          onConfirm={runAction}
          onCancel={() => setConfirming(null)}
        />
      )}
    </section>
  );
};

const Card = ({ title, icon, children, className = '' }) => (
  <section className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
    <h2 className="mb-4 flex items-center gap-2 text-base font-bold text-slate-900">
      <AdminIcon name={icon} className="h-5 w-5 text-slate-500" />
      {title}
    </h2>
    {children}
  </section>
);

const DetailList = ({ rows }) => (
  <dl className="divide-y divide-slate-100 text-sm">
    {rows.map(([label, value]) => (
      <div key={label} className="grid grid-cols-1 gap-1 py-2 sm:grid-cols-3 sm:gap-4">
        <dt className="font-medium text-slate-500">{label}</dt>
        <dd className="break-words text-slate-900 sm:col-span-2">{value}</dd>
      </div>
    ))}
  </dl>
);

const Note = ({ children }) => <p className="mt-3 text-xs text-slate-500">{children}</p>;

const AdminUserDetail = () => {
  const { uid = '' } = useParams();
  const location = useLocation();
  const validUid = isValidUid(uid);
  const [reloadCount, setReloadCount] = useState(0);
  const requestKey = `${uid}#${reloadCount}`;
  const [result, setResult] = useState({ key: null, data: null, error: null });

  useEffect(() => {
    if (!validUid) return undefined;
    let active = true;
    fetchAdminUser(uid)
      .then((data) => {
        if (!active) return;
        setResult(
          typeof data?.uid === 'string' && data.records
            ? { key: requestKey, data, error: null }
            : { key: requestKey, data: null, error: new AdminUsersRequestError(200, 'INVALID_RESPONSE') }
        );
      })
      .catch((error) => {
        // RequestErrorPanel handles sign-out for an expired session (401).
        if (active) setResult({ key: requestKey, data: null, error });
      });
    return () => {
      active = false;
    };
  }, [requestKey, uid, validUid]);

  // Return to the list with the same search and filters when we came from it.
  const from = location.state?.from;
  const backTo = `${ADMIN_USERS_PATH}${typeof from === 'string' && from.startsWith('?') ? from : ''}`;

  const backLink = (
    <Link
      to={backTo}
      className="inline-flex items-center gap-2 rounded-lg px-2 py-1 text-sm font-semibold text-blue-700 hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-blue-600"
    >
      <AdminIcon name="arrowLeft" className="h-4 w-4" />
      Back to users
    </Link>
  );

  if (!validUid) {
    return (
      <div className="space-y-4">
        {backLink}
        <RequestErrorPanel error={NOT_FOUND} backTo={backTo} />
      </div>
    );
  }

  // While refreshing (for example after an account action), keep showing this account's details.
  const refreshing = result.key !== requestKey;
  if (refreshing && result.data?.uid !== uid) {
    return (
      <div className="space-y-4">
        {backLink}
        <div role="status" aria-live="polite" className="flex items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white p-10 text-sm font-medium text-slate-600 shadow-sm">
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" aria-hidden="true" />
          Loading account details…
        </div>
      </div>
    );
  }

  if (!refreshing && result.error) {
    return (
      <div className="space-y-4">
        {backLink}
        <RequestErrorPanel error={result.error} onRetry={() => setReloadCount((n) => n + 1)} backTo={backTo} />
      </div>
    );
  }

  const user = result.data;
  const profile = user.profile;
  const results = user.records.results;
  const assessment = user.records.ai_assessment;
  const title = profile?.name || user.email || 'Account';
  const initial = (profile?.name || user.email || 'A').charAt(0).toUpperCase();

  return (
    <div className="space-y-6">
      {backLink}

      {/* Summary */}
      <section className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:flex-row sm:items-center">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xl font-bold text-white" aria-hidden="true">
          {initial}
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="break-words text-xl font-bold text-slate-900">{title}</h2>
          {user.email && <p className="break-all text-sm text-slate-600">{user.email}</p>}
          <div className="mt-2">
            <AccountBadges user={{ ...user, student_type: profile?.student_type ?? null }} profileMissing={!profile} />
          </div>
          <p className="mt-2 break-all font-mono text-xs text-slate-400">User ID: {user.uid}</p>
        </div>
      </section>

      <AccountAccessPanel
        key={user.uid}
        uid={user.uid}
        name={profile?.name || user.email}
        refreshKey={reloadCount}
        onChanged={() => setReloadCount((n) => n + 1)}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Account (Firebase Authentication) */}
        <Card title="Account" icon="lock">
          <DetailList
            rows={[
              ['Account type', user.is_admin ? 'Administrator (Firebase custom claim)' : 'Student'],
              ['Status', user.disabled ? 'Disabled' : 'Active'],
              ['Email verified', formatYesNo(user.email_verified)],
              ['Account created', formatDateTime(user.created_at)],
              ['Last sign-in', user.last_sign_in_at ? formatDateTime(user.last_sign_in_at) : 'Never'],
              ['Sign-in method', user.sign_in_providers.length ? user.sign_in_providers.map(getProviderLabel).join(', ') : '—'],
            ]}
          />
          <Note>From Firebase Authentication.</Note>
        </Card>

        {/* Student profile (Firestore users/{uid}) */}
        <Card title="Student profile" icon="users">
          {profile ? (
            <>
              <DetailList
                rows={[
                  ['Name', profile.name || '—'],
                  ['Student type', getStudentTypeLabel(profile.student_type)],
                  ['Registered', formatDateTime(profile.registered_at)],
                  ['Profile last updated', formatDateTime(profile.updated_at)],
                  ['Interests', profile.chosen_interests.length ? profile.chosen_interests.join(', ') : '—'],
                ]}
              />
              <h3 className="mt-5 mb-2 text-sm font-semibold text-slate-900">Learning journey</h3>
              <DetailList
                rows={[
                  ['Current step', getJourneyStepLabel(profile.current_step)],
                  ['Profile completed', formatYesNo(profile.progress.has_completed_profile)],
                  ['Results saved', formatYesNo(profile.progress.has_uploaded_results)],
                  ['Recommendations viewed', formatYesNo(profile.progress.has_viewed_recommendations)],
                  ['Preparation plan completed', formatYesNo(profile.progress.has_completed_preparation_plan)],
                ]}
              />
              {profile.student_type === 'legacy' && (
                <Note>This profile uses an older student-type value from a previous app version.</Note>
              )}
            </>
          ) : (
            <p className="text-sm text-slate-600">
              {user.is_admin
                ? 'No student profile. This is an administrator account.'
                : 'This account has no student profile in Firestore. The student may not have finished registering.'}
            </p>
          )}
        </Card>

        {/* Academic records: metadata only */}
        <Card title="Academic records" icon="criteria" className="lg:col-span-2">
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-900">SPM / exam results</h3>
              {results.exists ? (
                <>
                  <DetailList
                    rows={[
                      ['Subjects recorded', results.subject_count ?? '—'],
                      ['Last updated', formatDateTime(results.updated_at)],
                      ['Stored labels', [results.status, results.record_type, results.verification_method].filter(Boolean).join(' · ') || '—'],
                    ]}
                  />
                  <Note>Stored labels are written by the student&apos;s browser and are not independent verification.</Note>
                </>
              ) : (
                <p className="text-sm text-slate-600">No academic results saved.</p>
              )}
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-900">AI assessment</h3>
              {assessment.exists ? (
                <DetailList
                  rows={[
                    ['Questions answered', assessment.question_count ?? '—'],
                    ['Completed', formatDateTime(assessment.completed_at)],
                    ['Demo mode', formatYesNo(assessment.is_demo_mode)],
                  ]}
                />
              ) : (
                <p className="text-sm text-slate-600">No AI assessment saved.</p>
              )}
            </div>
          </div>
          <Note>Grades and assessment answers are not shown in the admin area.</Note>
        </Card>
      </div>

      <p className="flex items-start gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
        <AdminIcon name="lock" className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
        Account details are read-only. Disabling and enabling are in the Account access panel above. Deleting
        accounts is planned for a later milestone and is not available.
      </p>
    </div>
  );
};

export default AdminUserDetail;

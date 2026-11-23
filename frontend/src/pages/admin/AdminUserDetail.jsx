// frontend/src/pages/admin/AdminUserDetail.jsx
//
// Admin "User Details" (Milestone M3A) — READ ONLY.
// Data comes from GET /api/admin/users/{uid} (require_admin). Academic records are
// shown as metadata only: grades and assessment answers are never requested or shown.
// There are no account actions here (M3B is deferred).
import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import AdminIcon from '../../components/admin/AdminIcons';
import { ADMIN_USERS_PATH } from '../../components/admin/adminNavigation';
import { fetchAdminUser } from '../../utils/adminUsersApi';
import {
  AdminUsersRequestError,
  formatDateTime,
  formatYesNo,
  getJourneyStepLabel,
  getProviderLabel,
  getStudentTypeLabel,
  isValidUid,
} from '../../utils/adminUsers';
import { AccountBadges, RequestErrorPanel } from './AdminUsers';

const NOT_FOUND = new AdminUsersRequestError(404, 'USER_NOT_FOUND');

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

  if (result.key !== requestKey) {
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

  if (result.error) {
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
        Read-only view. Disabling, enabling and deleting accounts are planned for a later milestone (M3B) and are not
        available.
      </p>
    </div>
  );
};

export default AdminUserDetail;

// frontend/src/pages/admin/AdminUsers.jsx
//
// Admin "Manage Users" list (Milestone M3A) — READ ONLY.
// Data comes from GET /api/admin/users (require_admin; Firebase Admin SDK on the
// server). Search and filters live in the page URL so they survive opening a
// user's details and coming back. There are no account actions here (M3B is deferred).
import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import AdminIcon from '../../components/admin/AdminIcons';
import { fetchAdminUsers, signOutToLogin } from '../../utils/adminUsersApi';
import {
  AdminUsersRequestError,
  DEFAULT_PAGE_SIZE,
  MAX_SEARCH_LENGTH,
  PROFILE_FILTERS,
  STATUS_FILTERS,
  STUDENT_TYPE_FILTERS,
  buildListSearchParams,
  buildUserListQuery,
  describeUserRequestError,
  formatDateTime,
  getPageRange,
  getSignOutControls,
  getStudentTypeLabel,
  hasActiveFilters,
  normaliseSearch,
  readListFilters,
} from '../../utils/adminUsers';

const BADGE_TONES = {
  admin: 'bg-blue-50 text-blue-700 ring-blue-200',
  student: 'bg-slate-100 text-slate-700 ring-slate-200',
  active: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  disabled: 'bg-red-50 text-red-700 ring-red-200',
  warning: 'bg-amber-50 text-amber-800 ring-amber-200',
};

const Badge = ({ tone, children }) => (
  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${BADGE_TONES[tone]}`}>
    {children}
  </span>
);

// Account type, profile and status badges. Admin status comes from the server
// (Firebase custom claim), never from the student profile.
export const AccountBadges = ({ user, profileMissing }) => (
  <span className="flex flex-wrap gap-1.5">
    {user.is_admin && <Badge tone="admin">Administrator</Badge>}
    {!user.is_admin && user.student_type && <Badge tone="student">{getStudentTypeLabel(user.student_type)}</Badge>}
    {!user.is_admin && profileMissing && <Badge tone="warning">Profile missing</Badge>}
    {user.disabled ? <Badge tone="disabled">Disabled</Badge> : <Badge tone="active">Active</Badge>}
  </span>
);

// Inline error state for the Manage Users pages. An expired session (401) signs out
// automatically; "admin access not confirmed" (403) offers a Sign out button. The
// login page opens only after Firebase sign-out succeeds; if it fails, an error and
// a retry button are shown instead.
export const RequestErrorPanel = ({ error, onRetry, backTo }) => {
  const navigate = useNavigate();
  const info = describeUserRequestError(error);
  // 'idle' | 'pending' | 'failed'
  const [signOutStatus, setSignOutStatus] = useState(info.autoSignOut ? 'pending' : 'idle');
  const signOutControls = getSignOutControls(info, signOutStatus);

  useEffect(() => {
    if (info.autoSignOut) {
      signOutToLogin(navigate).catch(() => setSignOutStatus('failed'));
    }
  }, [info.autoSignOut, navigate]);

  const handleSignOut = () => {
    setSignOutStatus('pending');
    signOutToLogin(navigate).catch(() => setSignOutStatus('failed'));
  };

  return (
    <section role="alert" className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-600">
        <AdminIcon name={info.kind === 'server-unreachable' ? 'server' : 'alert'} className="h-6 w-6" />
      </div>
      <h2 className="mb-2 text-lg font-bold text-slate-900">{info.title}</h2>
      <p className="mx-auto max-w-md text-sm text-slate-600">{info.message}</p>
      {signOutControls?.progress && (
        <p className="mx-auto mt-2 max-w-md text-sm font-medium text-blue-700">{signOutControls.progress}</p>
      )}
      {signOutControls?.error && (
        <p className="mx-auto mt-3 max-w-md text-sm font-medium text-red-700">{signOutControls.error}</p>
      )}
      <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
        {info.retry && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 cursor-pointer"
          >
            Try again
          </button>
        )}
        {signOutControls?.button && (
          <button
            type="button"
            onClick={handleSignOut}
            disabled={signOutControls.button.disabled}
            className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 cursor-pointer"
          >
            {signOutControls.button.label}
          </button>
        )}
        {backTo && (
          <Link
            to={backTo}
            className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          >
            Back to users
          </Link>
        )}
      </div>
    </section>
  );
};

const LoadingBlock = ({ label }) => (
  <div role="status" aria-live="polite" className="flex items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white p-10 text-sm font-medium text-slate-600 shadow-sm">
    <span className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" aria-hidden="true" />
    {label}
  </div>
);

const SelectFilter = ({ id, label, value, options, allLabel, onChange }) => (
  <div>
    <label htmlFor={id} className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</label>
    <select
      id={id}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
    >
      <option value="">{allLabel}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  </div>
);

const Pagination = ({ page, totalPages, onPage }) => (
  <nav aria-label="Pagination" className="flex items-center justify-between gap-3">
    <button
      type="button"
      onClick={() => onPage(page - 1)}
      disabled={page <= 1}
      className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-blue-600 cursor-pointer"
    >
      Previous
    </button>
    <span className="text-sm text-slate-600">Page {page} of {totalPages}</span>
    <button
      type="button"
      onClick={() => onPage(page + 1)}
      disabled={page >= totalPages}
      className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-blue-600 cursor-pointer"
    >
      Next
    </button>
  </nav>
);

const detailsLinkClasses =
  'inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-semibold text-blue-700 transition hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-blue-600';

const AdminUsers = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const filters = readListFilters(searchParams);
  const requestQuery = buildUserListQuery({ ...filters, pageSize: DEFAULT_PAGE_SIZE });
  const [reloadCount, setReloadCount] = useState(0);
  const requestKey = `${requestQuery}#${reloadCount}`;
  // { key, data, error } for the most recent finished request.
  const [result, setResult] = useState({ key: null, data: null, error: null });

  useEffect(() => {
    let active = true;
    fetchAdminUsers(requestQuery)
      .then((data) => {
        if (!active) return;
        setResult(
          Array.isArray(data?.items)
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
  }, [requestKey, requestQuery]);

  const loading = result.key !== requestKey;
  const data = result.data;
  const filtersActive = hasActiveFilters(filters);

  const updateFilters = (changes) => setSearchParams(buildListSearchParams({ ...filters, page: 1, ...changes }));
  const clearFilters = () => setSearchParams(new URLSearchParams());
  const retry = () => setReloadCount((n) => n + 1);

  const handleSearch = (event) => {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get('search');
    updateFilters({ search: normaliseSearch(typeof value === 'string' ? value : '') });
  };

  let content;
  if (loading && !data) {
    content = <LoadingBlock label="Loading accounts…" />;
  } else if (!loading && result.error) {
    content = <RequestErrorPanel error={result.error} onRetry={retry} />;
  } else if (data) {
    const { from, to } = getPageRange({ page: data.page, pageSize: data.page_size, total: data.total });
    const items = data.items;

    content = (
      <div className={`space-y-4 transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
        <p className="text-sm text-slate-600" aria-live="polite">
          {data.total === 0
            ? 'No accounts to show.'
            : `Showing ${from}–${to} of ${data.total} account${data.total === 1 ? '' : 's'}${filtersActive ? ' matching your search or filters' : ''}.`}
          {loading && <span className="ml-2 font-medium text-blue-700">Updating…</span>}
        </p>

        {items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
              <AdminIcon name="users" className="h-6 w-6" />
            </div>
            <h2 className="font-semibold text-slate-900">
              {data.total > 0 ? 'No accounts on this page' : filtersActive ? 'No accounts match your search or filters' : 'No accounts found'}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {data.total > 0 ? 'Go back to the first page to see the results.' : filtersActive ? 'Try a different search or clear the filters.' : 'No Firebase Authentication accounts were returned.'}
            </p>
            {(filtersActive || data.total > 0) && (
              <button
                type="button"
                onClick={data.total > 0 ? () => updateFilters({}) : clearFilters}
                className="mt-4 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-600 cursor-pointer"
              >
                {data.total > 0 ? 'Go to first page' : 'Clear search and filters'}
              </button>
            )}
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm md:block">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <caption className="sr-only">Accounts, newest registration first</caption>
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th scope="col" className="px-4 py-3">Account</th>
                    <th scope="col" className="px-4 py-3">Type and status</th>
                    <th scope="col" className="px-4 py-3">Registered</th>
                    <th scope="col" className="px-4 py-3">Last sign-in</th>
                    <th scope="col" className="px-4 py-3"><span className="sr-only">Details</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((user) => (
                    <tr key={user.uid} className="align-top hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <p className="font-semibold text-slate-900">{user.name || 'No name recorded'}</p>
                        <p className="break-all text-slate-500">{user.email || 'No email address'}</p>
                      </td>
                      <td className="px-4 py-3">
                        <AccountBadges user={user} profileMissing={user.profile_status === 'missing'} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDateTime(user.created_at)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                        {user.last_sign_in_at ? formatDateTime(user.last_sign_in_at) : 'Never'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link to={`/admin/users/${encodeURIComponent(user.uid)}`} state={{ from: location.search }} className={detailsLinkClasses}>
                          View<span className="sr-only"> details for {user.email || user.name || 'this account'}</span>
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <ul className="space-y-3 md:hidden">
              {items.map((user) => (
                <li key={user.uid} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="font-semibold text-slate-900">{user.name || 'No name recorded'}</p>
                  <p className="break-all text-sm text-slate-500">{user.email || 'No email address'}</p>
                  <div className="mt-3">
                    <AccountBadges user={user} profileMissing={user.profile_status === 'missing'} />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">Registered {formatDateTime(user.created_at)}</p>
                  <Link
                    to={`/admin/users/${encodeURIComponent(user.uid)}`}
                    state={{ from: location.search }}
                    className={`${detailsLinkClasses} -ml-3 mt-2`}
                  >
                    View details<span className="sr-only"> for {user.email || user.name || 'this account'}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}

        {data.total > 0 && (
          <Pagination page={data.page} totalPages={data.total_pages} onPage={(page) => updateFilters({ page })} />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="admin-users-title">
        <h2 id="admin-users-title" className="text-lg font-bold text-slate-900">Accounts</h2>
        <p className="text-sm text-slate-600">
          Read-only view of student and administrator accounts, newest registration first. Account actions are not
          available yet.
        </p>
      </section>

      <form role="search" onSubmit={handleSearch} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <div className="md:col-span-2">
            <label htmlFor="admin-users-search" className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">
              Search by name or email
            </label>
            <div className="flex gap-2">
              <input
                key={filters.search}
                id="admin-users-search"
                name="search"
                type="search"
                defaultValue={filters.search}
                maxLength={MAX_SEARCH_LENGTH}
                placeholder="e.g. aisyah or @example.com"
                className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              />
              <button
                type="submit"
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 cursor-pointer"
              >
                Search
              </button>
            </div>
          </div>
          <SelectFilter id="admin-users-type" label="Student type" value={filters.studentType}
            options={STUDENT_TYPE_FILTERS} allLabel="All student types"
            onChange={(value) => updateFilters({ studentType: value })} />
          <SelectFilter id="admin-users-status" label="Account status" value={filters.status}
            options={STATUS_FILTERS} allLabel="All statuses"
            onChange={(value) => updateFilters({ status: value })} />
          <SelectFilter id="admin-users-profile" label="Student profile" value={filters.profile}
            options={PROFILE_FILTERS} allLabel="All profiles"
            onChange={(value) => updateFilters({ profile: value })} />
        </div>
        {filtersActive && (
          <button
            type="button"
            onClick={clearFilters}
            className="text-sm font-semibold text-blue-700 hover:underline focus-visible:outline-2 focus-visible:outline-blue-600 cursor-pointer"
          >
            Clear search and filters
          </button>
        )}
      </form>

      {data && data.complete === false && (
        <div role="note" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AdminIcon name="alert" className="mt-0.5 h-5 w-5 shrink-0" />
          <p>
            <span className="font-semibold">Results may be incomplete.</span> More than {data.account_limit} accounts
            exist; only the first {data.scanned_accounts} returned by Firebase were searched, filtered and sorted.
          </p>
        </div>
      )}

      {content}
    </div>
  );
};

export default AdminUsers;

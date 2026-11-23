// frontend/src/utils/adminUsers.js
//
// Helpers for the read-only Admin "Manage Users" pages (Milestone M3A): filter
// parsing from the page URL, API query building, labels and error descriptions.
// Plain JavaScript with no React or Firebase imports, so it can be tested with:
//   node --test src/utils/adminUsers.test.js
//
// Limits mirror backend/routes/admin_users.py; the backend validates every value again.
import { SIGN_OUT_FAILED_MESSAGE } from './signOutFlow.js';

export const USERS_API_PATH = '/api/admin/users';
export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 50;
export const MAX_SEARCH_LENGTH = 100;
const MAX_PAGE = 10000;
const UID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;

export const STUDENT_TYPE_FILTERS = Object.freeze([
  Object.freeze({ value: 'spm_leaver', label: 'SPM leaver' }),
  Object.freeze({ value: 'form_4_5', label: 'Form 4/5 student' }),
  Object.freeze({ value: 'legacy', label: 'Legacy student type' }),
  Object.freeze({ value: 'unknown', label: 'Unknown student type' }),
]);

export const STATUS_FILTERS = Object.freeze([
  Object.freeze({ value: 'active', label: 'Active' }),
  Object.freeze({ value: 'disabled', label: 'Disabled' }),
]);

export const PROFILE_FILTERS = Object.freeze([
  Object.freeze({ value: 'present', label: 'Profile present' }),
  Object.freeze({ value: 'missing', label: 'Profile missing' }),
]);

const valuesOf = (options) => new Set(options.map((option) => option.value));
const STUDENT_TYPE_VALUES = valuesOf(STUDENT_TYPE_FILTERS);
const STATUS_VALUES = valuesOf(STATUS_FILTERS);
const PROFILE_VALUES = valuesOf(PROFILE_FILTERS);

// Trims, collapses whitespace and limits the length of a search term.
export const normaliseSearch = (value) =>
  typeof value === 'string' ? value.trim().replace(/\s+/g, ' ').slice(0, MAX_SEARCH_LENGTH) : '';

const toPage = (value) => {
  const page = Number(value);
  return Number.isInteger(page) && page >= 1 && page <= MAX_PAGE ? page : 1;
};

// Reads list filters from the page URL. Unknown or invalid values are ignored.
export const readListFilters = (searchParams) => {
  const get = (key) => searchParams.get(key) ?? '';
  const pick = (value, allowed) => (allowed.has(value) ? value : '');
  return {
    search: normaliseSearch(get('search')),
    studentType: pick(get('student_type'), STUDENT_TYPE_VALUES),
    status: pick(get('status'), STATUS_VALUES),
    profile: pick(get('profile'), PROFILE_VALUES),
    page: toPage(get('page') || 1),
  };
};

const filterEntries = ({ search, studentType, status, profile }) => [
  ['search', normaliseSearch(search)],
  ['student_type', STUDENT_TYPE_VALUES.has(studentType) ? studentType : ''],
  ['status', STATUS_VALUES.has(status) ? status : ''],
  ['profile', PROFILE_VALUES.has(profile) ? profile : ''],
];

// Page URL parameters (empty values and page 1 are omitted).
export const buildListSearchParams = (filters) => {
  const params = new URLSearchParams();
  for (const [key, value] of filterEntries(filters)) {
    if (value) params.set(key, value);
  }
  const page = toPage(filters.page);
  if (page > 1) params.set('page', String(page));
  return params;
};

// Query string for GET /api/admin/users (always includes page and page_size).
export const buildUserListQuery = ({ pageSize = DEFAULT_PAGE_SIZE, ...filters } = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of filterEntries(filters)) {
    if (value) params.set(key, value);
  }
  const size = Number(pageSize);
  params.set('page', String(toPage(filters.page)));
  params.set('page_size', String(Number.isInteger(size) && size >= 1 && size <= MAX_PAGE_SIZE ? size : DEFAULT_PAGE_SIZE));
  return `?${params.toString()}`;
};

export const hasActiveFilters = (filters) =>
  Boolean(filters.search || filters.studentType || filters.status || filters.profile);

export const isValidUid = (uid) => typeof uid === 'string' && UID_PATTERN.test(uid);

const STUDENT_TYPE_LABELS = {
  spm_leaver: 'SPM leaver',
  form_4_5: 'Form 4/5 student',
  legacy: 'Legacy student type',
  unknown: 'Unknown student type',
};

export const getStudentTypeLabel = (type) => STUDENT_TYPE_LABELS[type] ?? 'No student profile';

const JOURNEY_STEP_LABELS = {
  1: 'Registered',
  2: 'Interests chosen',
  3: 'AI assessment completed',
  4: 'Recommendations viewed',
  5: 'Preparation plan opened',
};

// `currentStep` is written by the student pages (2 = interests ... 5 = preparation plan).
export const getJourneyStepLabel = (step) => JOURNEY_STEP_LABELS[step] ?? 'Not started';

const PROVIDER_LABELS = {
  password: 'Email and password',
  'google.com': 'Google',
  phone: 'Phone',
  anonymous: 'Anonymous',
};

export const getProviderLabel = (provider) => PROVIDER_LABELS[provider] ?? 'Other';

export const formatDateTime = (iso) => {
  if (typeof iso !== 'string' || !iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};

export const formatYesNo = (value) => {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  return '—';
};

// "Showing 21–40 of 57": item range for the current page.
export const getPageRange = ({ page, pageSize, total }) => {
  if (!total) return { from: 0, to: 0 };
  const from = (page - 1) * pageSize + 1;
  return from > total ? { from: 0, to: 0 } : { from, to: Math.min(total, page * pageSize) };
};

// Error thrown for non-success responses from the Manage Users endpoints.
export class AdminUsersRequestError extends Error {
  constructor(status, code = null) {
    super(`Manage Users request failed (HTTP ${status})`);
    this.name = 'AdminUsersRequestError';
    this.status = status;
    this.code = code;
  }
}

// What to show for a failed request. `signOut` offers signing out (see
// getSignOutControls); `autoSignOut` starts it automatically.
export const describeUserRequestError = (error) => {
  if (error?.name === 'ApiAuthError') {
    if (error.status === 401) {
      return { kind: 'session-expired', title: 'Session expired',
        message: 'Your session is no longer valid.', retry: false, signOut: true, autoSignOut: true };
    }
    if (error.status === 403) {
      return { kind: 'forbidden', title: 'Admin access not confirmed',
        message: 'The Route2UniKL server did not confirm administrator access for this account.', retry: false, signOut: true };
    }
    if (error.code === 'AUTH_SERVICE_UNAVAILABLE') {
      return { kind: 'auth-unavailable', title: 'Sign-in service temporarily unavailable',
        message: "We couldn't verify your sign-in right now. Please try again in a moment.", retry: true, signOut: false };
    }
  }
  if (error instanceof TypeError) {
    return { kind: 'server-unreachable', title: "Can't reach the Route2UniKL server",
      message: 'Check that the backend server is running, then try again.', retry: true, signOut: false };
  }
  if (error?.name === 'AdminUsersRequestError') {
    if (error.code === 'USER_NOT_FOUND' || error.status === 404) {
      return { kind: 'not-found', title: 'Account not found',
        message: 'No account exists with this ID. It may have been removed.', retry: false, signOut: false };
    }
    if (error.code === 'USER_SERVICE_UNAVAILABLE' || error.status === 503) {
      return { kind: 'service-unavailable', title: 'User information unavailable',
        message: 'Firebase could not be reached. Please try again in a moment.', retry: true, signOut: false };
    }
    if (error.status === 400 || error.status === 422) {
      return { kind: 'invalid-request', title: 'Search or filter not accepted',
        message: 'Clear the search and filters, then try again.', retry: false, signOut: false };
    }
  }
  return { kind: 'error', title: 'Something went wrong',
    message: "We couldn't load user information. Please try again.", retry: true, signOut: false };
};

// Shared sign-out helper and message (see signOutFlow.js): the login page opens
// only after sign-out succeeds; a failure rejects without navigating.
export { SIGN_OUT_FAILED_MESSAGE, signOutThenRedirect } from './signOutFlow.js';

// Sign-out controls for an error panel. `status` is 'idle', 'pending' or 'failed'.
// Returns null when the error needs no sign-out. A failed sign-out always shows an
// error and a retry button, and never claims that a redirect is happening.
export const getSignOutControls = (info, status) => {
  if (!info?.signOut) return null;
  if (status === 'failed') {
    return { progress: null, error: SIGN_OUT_FAILED_MESSAGE, button: { label: 'Try signing out again', disabled: false } };
  }
  if (info.autoSignOut) {
    return { progress: 'Signing you out and returning to the login page…', error: null, button: null };
  }
  return {
    progress: null,
    error: null,
    button: status === 'pending' ? { label: 'Signing out…', disabled: true } : { label: 'Sign out', disabled: false },
  };
};

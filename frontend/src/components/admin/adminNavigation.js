// frontend/src/components/admin/adminNavigation.js
//
// Single source of truth for the Admin area's modules: sidebar items, page titles
// and the dashboard's management overview. Plain JavaScript (no React), so it can
// be tested with Node's built-in test runner:
//   node --test src/components/admin/adminNavigation.test.js
//
// Only modules with `available: true` have a route. Planned modules (M3-M7) have
// no path, are rendered as disabled "Coming soon" items, and must not look
// functional until their milestone is implemented.

export const ADMIN_DASHBOARD_PATH = '/admin/dashboard';
export const ADMIN_NOT_FOUND_TITLE = 'Page not found';

export const ADMIN_NAV_ITEMS = Object.freeze([
  Object.freeze({
    key: 'dashboard',
    label: 'Dashboard',
    milestone: 'M2',
    available: true,
    path: ADMIN_DASHBOARD_PATH,
    icon: 'dashboard',
    description: 'Overview of the admin area and your access status.',
  }),
  Object.freeze({
    key: 'users',
    label: 'Manage Users',
    milestone: 'M3',
    available: false,
    path: null,
    icon: 'users',
    description: 'View and manage student and administrator accounts.',
  }),
  Object.freeze({
    key: 'programmes',
    label: 'Manage Programmes',
    milestone: 'M4',
    available: false,
    path: null,
    icon: 'programmes',
    description: 'Maintain the UniKL foundation programme catalogue.',
  }),
  Object.freeze({
    key: 'criteria',
    label: 'Programme Criteria',
    milestone: 'M5',
    available: false,
    path: null,
    icon: 'criteria',
    description: 'Maintain the eligibility criteria used for recommendations.',
  }),
  Object.freeze({
    key: 'resources',
    label: 'Preparatory Resources',
    milestone: 'M6',
    available: false,
    path: null,
    icon: 'resources',
    description: 'Maintain the preparatory learning resources for each programme.',
  }),
  Object.freeze({
    key: 'system',
    label: 'System Information',
    milestone: 'M7',
    available: false,
    path: null,
    icon: 'system',
    description: 'Manage system information and announcements.',
  }),
]);

// Modules shown as disabled "Coming soon" entries.
export const getUpcomingModules = () => ADMIN_NAV_ITEMS.filter((item) => !item.available);

// Label shown on a disabled module, e.g. "Coming soon · M3".
export const getComingSoonLabel = (item) => `Coming soon · ${item.milestone}`;

const normalisePath = (pathname) => {
  const trimmed = (pathname || '').replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
};

// Returns the available module matching the current path, or null.
// "/admin" counts as the dashboard because it redirects there.
export const findAdminNavItem = (pathname) => {
  const path = normalisePath(pathname);
  const target = path === '/admin' ? ADMIN_DASHBOARD_PATH : path;
  return ADMIN_NAV_ITEMS.find((item) => item.available && item.path === target) ?? null;
};

// Header title for the current admin path.
export const getAdminPageTitle = (pathname) => findAdminNavItem(pathname)?.label ?? ADMIN_NOT_FOUND_TITLE;

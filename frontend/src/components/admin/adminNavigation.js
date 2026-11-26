// frontend/src/components/admin/adminNavigation.js
//
// Single source of truth for the Admin area's modules: sidebar items, page titles
// and the dashboard's management overview. Plain JavaScript (no React), so it can
// be tested with Node's built-in test runner:
//   node --test src/components/admin/adminNavigation.test.js
//
// Only modules with `available: true` have a route. Planned modules (M4-M7) have
// no path, are rendered as disabled "Coming soon" items, and must not look
// functional until their milestone is implemented. A module with `detailTitle`
// also has one-level detail pages under its path (e.g. /admin/users/:uid).

export const ADMIN_DASHBOARD_PATH = '/admin/dashboard';
export const ADMIN_USERS_PATH = '/admin/users';
export const ADMIN_NOT_FOUND_TITLE = 'Page not found';

export const ADMIN_NAV_ITEMS = Object.freeze([
  Object.freeze({
    key: 'dashboard',
    label: 'Dashboard',
    milestone: 'M2',
    section: 'overview',
    available: true,
    path: ADMIN_DASHBOARD_PATH,
    icon: 'dashboard',
    description: 'Overview of the admin area and your access status.',
  }),
  Object.freeze({
    key: 'users',
    label: 'Manage Users',
    milestone: 'M3',
    section: 'management',
    available: true,
    path: ADMIN_USERS_PATH,
    detailTitle: 'User Details',
    icon: 'users',
    description: 'View accounts; disable, enable or delete student accounts (local emulator only).',
  }),
  Object.freeze({
    key: 'programmes',
    label: 'Manage Programmes',
    milestone: 'M4',
    section: 'management',
    available: false,
    path: null,
    icon: 'programmes',
    description: 'Maintain the UniKL foundation programme catalogue.',
  }),
  Object.freeze({
    key: 'criteria',
    label: 'Programme Criteria',
    milestone: 'M5',
    section: 'management',
    available: false,
    path: null,
    icon: 'criteria',
    description: 'Maintain the eligibility criteria used for recommendations.',
  }),
  Object.freeze({
    key: 'resources',
    label: 'Preparatory Resources',
    milestone: 'M6',
    section: 'management',
    available: false,
    path: null,
    icon: 'resources',
    description: 'Maintain the preparatory learning resources for each programme.',
  }),
  Object.freeze({
    key: 'system',
    label: 'System Information',
    milestone: 'M7',
    section: 'management',
    available: false,
    path: null,
    icon: 'system',
    description: 'Manage system information and announcements.',
  }),
]);

// Modules shown as disabled "Coming soon" entries.
export const getUpcomingModules = () => ADMIN_NAV_ITEMS.filter((item) => !item.available);

// Sidebar groups, in order.
export const getNavSection = (section) => ADMIN_NAV_ITEMS.filter((item) => item.section === section);

// Label shown on a disabled module, e.g. "Coming soon · M4".
export const getComingSoonLabel = (item) => `Coming soon · ${item.milestone}`;

const normalisePath = (pathname) => {
  const trimmed = (pathname || '').replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
};

// True for exactly one path segment below the module path, e.g. /admin/users/abc.
const isDetailPath = (item, path) => {
  if (!item.detailTitle || !path.startsWith(`${item.path}/`)) return false;
  const rest = path.slice(item.path.length + 1);
  return rest.length > 0 && !rest.includes('/');
};

// Returns the available module matching the current path (its page or a detail
// page), or null. "/admin" counts as the dashboard because it redirects there.
export const findAdminNavItem = (pathname) => {
  const path = normalisePath(pathname);
  const target = path === '/admin' ? ADMIN_DASHBOARD_PATH : path;
  return ADMIN_NAV_ITEMS.find((item) => item.available && (item.path === target || isDetailPath(item, target))) ?? null;
};

// Header title for the current admin path.
export const getAdminPageTitle = (pathname) => {
  const path = normalisePath(pathname);
  const target = path === '/admin' ? ADMIN_DASHBOARD_PATH : path;
  const item = findAdminNavItem(target);
  if (!item) return ADMIN_NOT_FOUND_TITLE;
  return item.path === target ? item.label : item.detailTitle;
};

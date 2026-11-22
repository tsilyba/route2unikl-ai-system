// frontend/src/components/admin/adminNavigation.test.js
//
// Tests for the Admin module configuration. No browser or Firebase.
// Run from the frontend folder:
//   node --test src/components/admin/adminNavigation.test.js
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ADMIN_DASHBOARD_PATH,
  ADMIN_NAV_ITEMS,
  ADMIN_NOT_FOUND_TITLE,
  findAdminNavItem,
  getAdminPageTitle,
  getComingSoonLabel,
  getUpcomingModules,
} from './adminNavigation.js';

describe('Admin module configuration', () => {
  test('lists the six modules in roadmap order with their milestones', () => {
    assert.deepEqual(
      ADMIN_NAV_ITEMS.map((item) => [item.key, item.label, item.milestone]),
      [
        ['dashboard', 'Dashboard', 'M2'],
        ['users', 'Manage Users', 'M3'],
        ['programmes', 'Manage Programmes', 'M4'],
        ['criteria', 'Programme Criteria', 'M5'],
        ['resources', 'Preparatory Resources', 'M6'],
        ['system', 'System Information', 'M7'],
      ]
    );
  });

  test('keys and labels are unique, and every module has an icon and description', () => {
    assert.equal(new Set(ADMIN_NAV_ITEMS.map((i) => i.key)).size, ADMIN_NAV_ITEMS.length);
    assert.equal(new Set(ADMIN_NAV_ITEMS.map((i) => i.label)).size, ADMIN_NAV_ITEMS.length);
    for (const item of ADMIN_NAV_ITEMS) {
      assert.ok(item.icon, `${item.key} icon`);
      assert.ok(item.description, `${item.key} description`);
    }
  });

  test('the configuration cannot be modified at runtime', () => {
    assert.ok(Object.isFrozen(ADMIN_NAV_ITEMS));
    assert.ok(ADMIN_NAV_ITEMS.every((item) => Object.isFrozen(item)));
  });
});

describe('Dashboard is the only available module (M2)', () => {
  test('only the dashboard is available, at /admin/dashboard', () => {
    const available = ADMIN_NAV_ITEMS.filter((item) => item.available);
    assert.equal(available.length, 1);
    assert.equal(available[0].key, 'dashboard');
    assert.equal(available[0].path, ADMIN_DASHBOARD_PATH);
    assert.equal(ADMIN_DASHBOARD_PATH, '/admin/dashboard');
  });

  test('M3-M7 modules are disabled and have no route', () => {
    const upcoming = getUpcomingModules();
    assert.deepEqual(upcoming.map((item) => item.milestone), ['M3', 'M4', 'M5', 'M6', 'M7']);
    for (const item of upcoming) {
      assert.equal(item.available, false, item.key);
      assert.equal(item.path, null, item.key);
    }
  });

  test('disabled modules carry a clear "Coming soon" label with their milestone', () => {
    assert.deepEqual(
      getUpcomingModules().map(getComingSoonLabel),
      ['Coming soon · M3', 'Coming soon · M4', 'Coming soon · M5', 'Coming soon · M6', 'Coming soon · M7']
    );
  });
});

describe('Active navigation and page titles', () => {
  test('the dashboard path resolves to the dashboard item (active navigation)', () => {
    for (const path of ['/admin/dashboard', '/admin/dashboard/', '/admin', '/admin/']) {
      assert.equal(findAdminNavItem(path)?.key, 'dashboard', path);
    }
  });

  test('unfinished or unknown paths resolve to no item', () => {
    for (const path of ['/admin/users', '/admin/programmes', '/admin/criteria', '/admin/resources',
      '/admin/system', '/admin/unknown', '/dashboard', '/', '', undefined]) {
      assert.equal(findAdminNavItem(path), null, String(path));
    }
  });

  test('page titles resolve for the dashboard and fall back to "Page not found"', () => {
    assert.equal(getAdminPageTitle('/admin/dashboard'), 'Dashboard');
    assert.equal(getAdminPageTitle('/admin'), 'Dashboard');
    assert.equal(ADMIN_NOT_FOUND_TITLE, 'Page not found');
    for (const path of ['/admin/users', '/admin/system', '/admin/anything/else']) {
      assert.equal(getAdminPageTitle(path), ADMIN_NOT_FOUND_TITLE, path);
    }
  });
});

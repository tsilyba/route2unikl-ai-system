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
  ADMIN_USERS_PATH,
  findAdminNavItem,
  getAdminPageTitle,
  getComingSoonLabel,
  getNavSection,
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

  test('keys and labels are unique, and every module has an icon, description and section', () => {
    assert.equal(new Set(ADMIN_NAV_ITEMS.map((i) => i.key)).size, ADMIN_NAV_ITEMS.length);
    assert.equal(new Set(ADMIN_NAV_ITEMS.map((i) => i.label)).size, ADMIN_NAV_ITEMS.length);
    for (const item of ADMIN_NAV_ITEMS) {
      assert.ok(item.icon, `${item.key} icon`);
      assert.ok(item.description, `${item.key} description`);
      assert.ok(['overview', 'management'].includes(item.section), `${item.key} section`);
    }
  });

  test('Manage Users is no longer described as read-only (M3C)', () => {
    const users = ADMIN_NAV_ITEMS.find((item) => item.key === 'users');
    assert.doesNotMatch(users.description, /read-only/i);
    assert.match(users.description, /disable, enable or delete student accounts \(local emulator only\)/);
  });

  test('the configuration cannot be modified at runtime', () => {
    assert.ok(Object.isFrozen(ADMIN_NAV_ITEMS));
    assert.ok(ADMIN_NAV_ITEMS.every((item) => Object.isFrozen(item)));
  });

  test('sidebar sections: Dashboard under Overview, all management modules under Management', () => {
    assert.deepEqual(getNavSection('overview').map((i) => i.key), ['dashboard']);
    assert.deepEqual(getNavSection('management').map((i) => i.key),
      ['users', 'programmes', 'criteria', 'resources', 'system']);
  });
});

describe('Available modules (M2 Dashboard, M3A Manage Users)', () => {
  test('only the dashboard and Manage Users are available, at their paths', () => {
    const available = ADMIN_NAV_ITEMS.filter((item) => item.available);
    assert.deepEqual(available.map((i) => [i.key, i.path]), [
      ['dashboard', '/admin/dashboard'],
      ['users', '/admin/users'],
    ]);
    assert.equal(ADMIN_DASHBOARD_PATH, '/admin/dashboard');
    assert.equal(ADMIN_USERS_PATH, '/admin/users');
  });

  test('M4-M7 modules are disabled and have no route', () => {
    const upcoming = getUpcomingModules();
    assert.deepEqual(upcoming.map((item) => item.milestone), ['M4', 'M5', 'M6', 'M7']);
    for (const item of upcoming) {
      assert.equal(item.available, false, item.key);
      assert.equal(item.path, null, item.key);
    }
  });

  test('disabled modules carry a clear "Coming soon" label with their milestone', () => {
    assert.deepEqual(
      getUpcomingModules().map(getComingSoonLabel),
      ['Coming soon · M4', 'Coming soon · M5', 'Coming soon · M6', 'Coming soon · M7']
    );
  });
});

describe('Active navigation and page titles', () => {
  test('dashboard paths resolve to the dashboard item', () => {
    for (const path of ['/admin/dashboard', '/admin/dashboard/', '/admin', '/admin/']) {
      assert.equal(findAdminNavItem(path)?.key, 'dashboard', path);
    }
  });

  test('Manage Users and its detail pages resolve to the users item (active navigation)', () => {
    for (const path of ['/admin/users', '/admin/users/', '/admin/users/abc123', '/admin/users/abc_DEF-9/']) {
      assert.equal(findAdminNavItem(path)?.key, 'users', path);
    }
  });

  test('unfinished, nested or unknown paths resolve to no item', () => {
    for (const path of ['/admin/usersx', '/admin/users/abc/extra', '/admin/programmes', '/admin/criteria',
      '/admin/resources', '/admin/system', '/admin/unknown', '/admin/dashboard/x', '/dashboard', '/', '', undefined]) {
      assert.equal(findAdminNavItem(path), null, String(path));
    }
  });

  test('page titles resolve and fall back to "Page not found"', () => {
    assert.equal(getAdminPageTitle('/admin/dashboard'), 'Dashboard');
    assert.equal(getAdminPageTitle('/admin'), 'Dashboard');
    assert.equal(getAdminPageTitle('/admin/users'), 'Manage Users');
    assert.equal(getAdminPageTitle('/admin/users/abc123'), 'User Details');
    assert.equal(ADMIN_NOT_FOUND_TITLE, 'Page not found');
    for (const path of ['/admin/users/abc/extra', '/admin/programmes', '/admin/system', '/admin/anything/else']) {
      assert.equal(getAdminPageTitle(path), ADMIN_NOT_FOUND_TITLE, path);
    }
  });
});

// frontend/src/components/admin/AdminSidebar.jsx
//
// Admin navigation. Rendered twice by AdminLayout:
//   - variant="desktop": fixed 256px sidebar, visible from the lg breakpoint;
//   - variant="mobile":  slide-in dialog with focus trap (opened from the header menu).
// Available modules are links (aria-current marks the active page). Planned
// modules (M3-M7) are plain, non-focusable text with a "Coming soon" label.
import { useEffect, useRef } from 'react';
import { NavLink } from 'react-router-dom';
import AdminIcon from './AdminIcons';
import { ADMIN_NAV_ITEMS, getComingSoonLabel } from './adminNavigation';

const linkClasses = ({ isActive }) =>
  [
    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400',
    isActive ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-300 hover:bg-slate-800 hover:text-white',
  ].join(' ');

const NavItems = ({ onNavigate }) => {
  const available = ADMIN_NAV_ITEMS.filter((item) => item.available);
  const upcoming = ADMIN_NAV_ITEMS.filter((item) => !item.available);

  return (
    <>
      <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Overview</p>
      <ul className="space-y-1">
        {available.map((item) => (
          <li key={item.key}>
            <NavLink to={item.path} end className={linkClasses} onClick={onNavigate}>
              <AdminIcon name={item.icon} />
              <span>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      <p className="mt-6 px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Management</p>
      <ul className="space-y-1">
        {upcoming.map((item) => (
          <li key={item.key}>
            <div
              className="flex cursor-not-allowed select-none items-start gap-3 rounded-lg px-3 py-2 text-slate-500"
              aria-disabled="true"
              title={`${item.label} is not available yet (${item.milestone})`}
            >
              <AdminIcon name={item.icon} className="mt-0.5 h-5 w-5 shrink-0" />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{item.label}</span>
                <span className="mt-0.5 inline-block rounded-full bg-slate-800 px-2 py-0.5 text-[11px] font-semibold text-slate-400">
                  {getComingSoonLabel(item)}
                </span>
              </span>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
};

const Brand = () => (
  <div className="flex items-center gap-3">
    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white" aria-hidden="true">
      <AdminIcon name="shield" className="h-5 w-5" />
    </div>
    <div className="leading-tight">
      <p className="text-base font-bold text-white">Route2UniKL</p>
      <p className="text-xs font-semibold uppercase tracking-wider text-blue-300">Admin</p>
    </div>
  </div>
);

const LogoutButton = ({ onLogout }) => (
  <button
    type="button"
    onClick={onLogout}
    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-red-600 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 cursor-pointer"
  >
    <AdminIcon name="logout" />
    <span>Log out</span>
  </button>
);

const FOCUSABLE = 'a[href], button:not([disabled])';

const AdminSidebar = ({ variant, onLogout, onNavigate, onClose }) => {
  const panelRef = useRef(null);
  const closeButtonRef = useRef(null);
  const isMobile = variant === 'mobile';

  // Mobile dialog: move focus into the panel when it opens.
  useEffect(() => {
    if (isMobile) closeButtonRef.current?.focus();
  }, [isMobile]);

  // Mobile dialog: keep Tab / Shift+Tab inside the panel while it is open.
  const handleKeyDown = (event) => {
    if (!isMobile || event.key !== 'Tab' || !panelRef.current) return;
    const focusable = Array.from(panelRef.current.querySelectorAll(FOCUSABLE));
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (isMobile) {
    return (
      <div
        id="admin-mobile-nav"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Admin navigation"
        onKeyDown={handleKeyDown}
        className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col bg-slate-900 shadow-2xl lg:hidden"
      >
        <div className="flex h-16 items-center justify-between border-b border-slate-800 px-4">
          <Brand />
          <button
            type="button"
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Close navigation menu"
            className="rounded-lg p-2 text-slate-300 hover:bg-slate-800 hover:text-white focus-visible:outline-2 focus-visible:outline-blue-400 cursor-pointer"
          >
            <AdminIcon name="close" />
          </button>
        </div>
        <nav aria-label="Admin" className="flex-1 overflow-y-auto px-3 py-5">
          <NavItems onNavigate={onNavigate} />
        </nav>
        <div className="border-t border-slate-800 p-3">
          <LogoutButton onLogout={onLogout} />
        </div>
      </div>
    );
  }

  return (
    <aside className="hidden bg-slate-900 lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:flex lg:w-64 lg:flex-col">
      <div className="flex h-16 items-center border-b border-slate-800 px-5">
        <Brand />
      </div>
      <nav aria-label="Admin" className="flex-1 overflow-y-auto px-3 py-5">
        <NavItems onNavigate={onNavigate} />
      </nav>
      <div className="border-t border-slate-800 p-3">
        <LogoutButton onLogout={onLogout} />
      </div>
    </aside>
  );
};

export default AdminSidebar;

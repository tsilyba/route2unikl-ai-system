// frontend/src/components/admin/AdminHeader.jsx
//
// Admin top bar: mobile menu toggle, page title, signed-in Admin account and logout.
import AdminIcon from './AdminIcons';

const AdminHeader = ({ title, email, mobileNavOpen, onMenuClick, menuButtonRef, onLogout }) => {
  const initial = email ? email.charAt(0).toUpperCase() : 'A';

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/95 px-4 backdrop-blur sm:px-6 lg:px-8">
      <button
        type="button"
        ref={menuButtonRef}
        onClick={onMenuClick}
        aria-label="Open navigation menu"
        aria-expanded={mobileNavOpen}
        aria-controls="admin-mobile-nav"
        className="-ml-1 rounded-lg p-2 text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-600 lg:hidden cursor-pointer"
      >
        <AdminIcon name="menu" className="h-6 w-6" />
      </button>

      <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-slate-900">{title}</h1>

      <div className="flex min-w-0 items-center gap-3">
        <div className="hidden min-w-0 text-right sm:block">
          {email && (
            <p className="max-w-[16rem] truncate text-sm font-medium text-slate-800" title={email}>
              {email}
            </p>
          )}
          <p className="text-xs text-slate-500">Administrator</p>
        </div>
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white"
          aria-hidden="true"
        >
          {initial}
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-red-200 hover:bg-red-50 hover:text-red-700 focus-visible:outline-2 focus-visible:outline-blue-600 cursor-pointer"
        >
          <AdminIcon name="logout" className="h-4 w-4" />
          <span className="hidden sm:inline">Log out</span>
          <span className="sr-only sm:hidden">Log out</span>
        </button>
      </div>
    </header>
  );
};

export default AdminHeader;

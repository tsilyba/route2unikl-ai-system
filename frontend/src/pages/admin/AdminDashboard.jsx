// frontend/src/pages/admin/AdminDashboard.jsx
//
// Admin Dashboard (Milestone 2). Rendered inside AdminLayout, which only shows
// admin content after the Firebase claim check and the server check
// (GET /api/admin/verify) have both succeeded.
//
// No statistics are shown: management data arrives with modules M3-M7. Every
// fact displayed here (email, verification status and time) was actually recorded.
import { useOutletContext } from 'react-router-dom';
import AdminIcon from '../../components/admin/AdminIcons';
import { getComingSoonLabel, getUpcomingModules } from '../../components/admin/adminNavigation';

const formatVerifiedAt = (date) =>
  date instanceof Date ? date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' }) : null;

const StatusItem = ({ icon, title, detail, tone = 'success' }) => (
  <li className="flex items-start gap-3">
    <span
      className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
        tone === 'success' ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-500'
      }`}
    >
      <AdminIcon name={icon} className="h-5 w-5" />
    </span>
    <span className="min-w-0">
      <span className="block text-sm font-semibold text-slate-900">{title}</span>
      <span className="block text-sm text-slate-600">{detail}</span>
    </span>
  </li>
);

const AdminDashboard = () => {
  const { verification } = useOutletContext() ?? {};
  const email = verification?.email;
  const verifiedAt = formatVerifiedAt(verification?.verifiedAt);
  const upcoming = getUpcomingModules();

  return (
    <div className="space-y-8">
      {/* Welcome */}
      <section className="rounded-2xl bg-blue-600 p-6 text-white shadow-lg sm:p-8" aria-labelledby="admin-welcome-title">
        <h2 id="admin-welcome-title" className="text-2xl font-bold sm:text-3xl">Welcome back, Administrator</h2>
        {email && (
          <p className="mt-2 break-all text-blue-100">
            Signed in as <span className="font-semibold text-white">{email}</span>
          </p>
        )}
        <p className="mt-4 inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1 text-sm font-semibold">
          <AdminIcon name="shield" className="h-4 w-4" />
          Admin access confirmed by the server
        </p>
      </section>

      <div className="grid gap-8 xl:grid-cols-3">
        {/* Management overview */}
        <section className="xl:col-span-2" aria-labelledby="admin-modules-title">
          <h2 id="admin-modules-title" className="text-lg font-bold text-slate-900">Management overview</h2>
          <p className="mb-4 text-sm text-slate-600">
            These management modules are planned for upcoming milestones and are not available yet.
          </p>
          <ul className="grid gap-4 sm:grid-cols-2">
            {upcoming.map((item) => (
              <li key={item.key} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
                    <AdminIcon name={item.icon} />
                  </span>
                  <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
                    {getComingSoonLabel(item)}
                  </span>
                </div>
                <h3 className="font-semibold text-slate-900">{item.label}</h3>
                <p className="mt-1 text-sm text-slate-600">{item.description}</p>
                <p className="mt-4 text-xs font-medium text-slate-400">Not available yet</p>
              </li>
            ))}
          </ul>
        </section>

        {/* Access status */}
        <section aria-labelledby="admin-access-title">
          <h2 id="admin-access-title" className="text-lg font-bold text-slate-900">Access status</h2>
          <p className="mb-4 text-sm text-slate-600">How your administrator access was confirmed.</p>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <ul className="space-y-4">
              <StatusItem
                icon="check"
                title="Firebase admin claim verified"
                detail="Your sign-in token carries the administrator claim (checked when the admin area opened)."
              />
              <StatusItem
                icon="check"
                title="Backend admin verification successful"
                detail="The Route2UniKL server confirmed your administrator access."
              />
              {verifiedAt && (
                <StatusItem
                  icon="clock"
                  tone="neutral"
                  title="Server verification time"
                  detail={`${verifiedAt} (this device's clock)`}
                />
              )}
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
};

export default AdminDashboard;

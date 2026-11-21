// frontend/src/pages/admin/AdminDashboard.jsx
//
// TEMPORARY PLACEHOLDER (Milestone 1 — Admin Authentication & RBAC).
// Exists only so the protected /admin/dashboard route has a destination.
// The real Admin Dashboard UI is built in Milestone 2.
import { auth } from '../../firebase';

const AdminDashboard = () => {
  const email = auth.currentUser?.email;

  return (
    <div className="flex items-center justify-center min-h-[60vh] px-4">
      <div className="p-8 bg-white rounded-xl shadow-lg w-full max-w-md border border-gray-100 text-center">
        <h2 className="text-3xl font-bold mb-3 text-blue-600">Route2UniKL Admin</h2>
        <p className="text-gray-700 mb-2">Admin access verified.</p>
        {email && (
          <p className="text-sm text-gray-500 mb-4">
            Signed in as <span className="font-semibold">{email}</span>
          </p>
        )}
        <p className="text-xs text-gray-400">
          Placeholder page — the Admin Dashboard will be built in the next milestone.
        </p>
      </div>
    </div>
  );
};

export default AdminDashboard;

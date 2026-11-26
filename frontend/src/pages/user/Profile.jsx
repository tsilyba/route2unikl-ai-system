import React, { useState, useEffect } from 'react';
import { auth, db, useEmulators } from '../../firebase';
import { doc, getDoc, updateDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';
import { EmailAuthProvider, reauthenticateWithCredential, signOut } from 'firebase/auth';
import { authFetch } from '../../utils/apiClient';
import { SELF_DELETE_TEXT, describeReauthError, requestOwnAccountDeletion } from '../../utils/selfDeletion';

const Profile = () => {
  const [userData, setUserData] = useState({
    name: '',
    email: '',
    role: '',
  });
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  // Account deletion (M3C): a protected backend workflow, local emulators only for now.
  const [showDelete, setShowDelete] = useState(false);
  const [password, setPassword] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteFeedback, setDeleteFeedback] = useState(null);
  const navigate = useNavigate();
  const user = auth.currentUser;

  //roles label
  const roleLabels = {
    spm_leaver: "SPM Leaver",
    form_4_5: "Upper Secondary Student",
  };
  // READ: Fetch user data from Firestore
  useEffect(() => {
    const fetchUserData = async () => {
      if (user) {
        const docRef = doc(db, "users", user.uid);
        const docSnap = await getDoc(docRef);

        if (docSnap.exists()) {
          setUserData(docSnap.data());
        }
        setLoading(false);
      }
    };
    fetchUserData();
  }, [user]);

  // UPDATE: Save changes to Firestore
  const handleUpdate = async (e) => {
    e.preventDefault();
    try {
      const docRef = doc(db, "users", user.uid);
      await updateDoc(docRef, userData);
      setIsEditing(false);
      alert("Profile updated successfully! ✨");
    } catch (error) {
      console.error("Error updating profile:", error);
    }
  };

  // DELETE (M3C): the browser never deletes documents or the Auth account itself. The student confirms their
  // password (the server requires a recent sign-in), the backend runs the protected deletion
  // (POST /api/account/delete, local emulators only), and the browser signs out only after the server
  // reports the deletion complete. A failure never leaves a partial browser-side deletion.
  const handleDeleteAccount = async (e) => {
    e.preventDefault();
    if (!user || deleting || !password) return;
    setDeleting(true);
    setDeleteFeedback(null);
    try {
      await reauthenticateWithCredential(user, EmailAuthProvider.credential(user.email, password));
      await user.getIdToken(true); // a token carrying the new sign-in time
    } catch (error) {
      setPassword('');
      setDeleteFeedback(describeReauthError(error));
      setDeleting(false);
      return;
    }
    setPassword('');
    const outcome = await requestOwnAccountDeletion({ uid: user.uid, authFetch });
    if (!outcome.ok) {
      setDeleteFeedback(outcome);
      setDeleting(false);
      return;
    }
    try {
      await signOut(auth);
    } catch {
      setDeleteFeedback({ tone: 'warning', title: outcome.title, message: SELF_DELETE_TEXT.signOutFailed });
      setDeleting(false);
      return;
    }
    navigate('/login', { replace: true });
  };

  const cancelDelete = () => {
    setShowDelete(false);
    setPassword('');
    setDeleteFeedback(null);
  };

  const feedbackClass = {
    success: 'bg-green-50 border-green-200 text-green-800',
    warning: 'bg-amber-50 border-amber-200 text-amber-800',
    error: 'bg-red-50 border-red-200 text-red-700',
  };

  if (loading) return <div className="p-20 text-center">Loading Profile...</div>;

  return (
    
    <div className="max-w-4xl mx-auto p-6 mt-10">
      <div className="bg-white shadow-xl rounded-3xl overflow-hidden border border-gray-100">
        <div className="p-8 pt-12">
          <div className="flex justify-between items-center mb-8">
            <h1 className="text-3xl font-bold text-gray-800">My Profile</h1>
            <button 
              onClick={() => setIsEditing(!isEditing)}
              className="px-6 py-2 rounded-xl font-bold transition border border-blue-600 text-blue-600 hover:bg-blue-50"
            >
              {isEditing ? "Cancel" : "Edit Profile"}
            </button>
          </div>

          {isEditing ? (
            /* UPDATE FORM */
            <form onSubmit={handleUpdate} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-bold text-gray-400 mb-2">FULL NAME</label>
                  <input 
                    type="text"
                    className="w-full p-3 bg-gray-50 rounded-xl border focus:ring-2 focus:ring-blue-500 outline-none"
                    value={userData.name}
                    onChange={(e) => setUserData({...userData, name: e.target.value})}
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-gray-400 mb-2">EMAIL (READ ONLY)</label>
                  <input 
                    type="text"
                    disabled
                    className="w-full p-3 bg-gray-100 rounded-xl border text-gray-400 cursor-not-allowed"
                    value={user.email}
                  />
                </div>
              </div>
              <button type="submit" className="w-full py-4 bg-blue-600 text-white rounded-2xl font-bold shadow-lg hover:bg-blue-700 transition">
                Save Changes
              </button>
            </form>
          ) : (
            /* READ VIEW */
            <div className="space-y-8">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div>
                  <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-1">Name</p>
                  <p className="text-xl text-gray-800 font-semibold">{userData.name || "N/A"}</p>
                </div>
                <div>
                  <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-1">Email</p>
                  <p className="text-xl text-gray-800 font-semibold">{user.email}</p>
                </div>
                 <div>
                  <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-1">Role</p>
                  <p className="text-xl text-gray-800 font-semibold">{userData.role ? roleLabels[userData.role] : "N/A"}</p>
                </div>
              </div>

              {/* Danger Zone */}
              <div className="mt-12 pt-8 border-t border-red-50">
                {!useEmulators ? (
                  <p className="text-sm text-gray-500">{SELF_DELETE_TEXT.productionUnavailable}</p>
                ) : !showDelete ? (
                  <button
                    type="button"
                    onClick={() => setShowDelete(true)}
                    className="text-sm font-bold text-red-400 hover:text-red-600 transition"
                  >
                    Delete Account
                  </button>
                ) : (
                  <form onSubmit={handleDeleteAccount} className="space-y-4 max-w-md">
                    <p className="text-sm font-semibold text-red-700">{SELF_DELETE_TEXT.warning}</p>
                    <div>
                      <label htmlFor="delete-password" className="block text-sm font-bold text-gray-500 mb-2">
                        {SELF_DELETE_TEXT.passwordLabel}
                      </label>
                      <input
                        id="delete-password"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        disabled={deleting}
                        onChange={(e) => setPassword(e.target.value)}
                        className="w-full p-3 bg-gray-50 rounded-xl border focus:ring-2 focus:ring-red-500 outline-none"
                      />
                    </div>
                    {deleteFeedback && (
                      <div role="alert" className={`p-3 rounded-xl border text-sm ${feedbackClass[deleteFeedback.tone] ?? feedbackClass.error}`}>
                        <p className="font-bold">{deleteFeedback.title}</p>
                        <p>{deleteFeedback.message}</p>
                      </div>
                    )}
                    <div className="flex gap-3">
                      <button
                        type="submit"
                        disabled={deleting || !password}
                        className="px-5 py-2 rounded-xl font-bold text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
                      >
                        {deleting ? SELF_DELETE_TEXT.pendingLabel : SELF_DELETE_TEXT.confirmLabel}
                      </button>
                      <button
                        type="button"
                        onClick={cancelDelete}
                        disabled={deleting}
                        className="px-5 py-2 rounded-xl font-bold text-gray-600 border border-gray-300 hover:bg-gray-50 disabled:opacity-50 transition"
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Profile;
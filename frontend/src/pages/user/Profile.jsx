import React, { useState, useEffect } from 'react';
import { auth, db } from '../../firebase';
import { doc, getDoc, updateDoc, deleteDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';
import { deleteUser } from 'firebase/auth';

const Profile = () => {
  const [userData, setUserData] = useState({
    name: '',
    email: '',
    role: '',
  });
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);
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

  // DELETE: Remove account and data
  const handleDeleteAccount = async () => {
    const confirmDelete = window.confirm("Are you sure? This will permanently delete your account and data.");
    if (confirmDelete) {
      try {
        // Delete from Firestore
        await deleteDoc(doc(db, "users", user.uid));
        // Delete from Auth
        await deleteUser(user);
        navigate('/login');
      } catch (error) {
        console.error("Error deleting account:", error);
        alert("Please re-login to delete your account for security reasons.");
      }
    }
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
                <button 
                  onClick={handleDeleteAccount}
                  className="text-sm font-bold text-red-400 hover:text-red-600 transition"
                >
                  Delete Account
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Profile;
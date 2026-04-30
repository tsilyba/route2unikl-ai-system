// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";




// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyCqktUI68_viIr_pvHnbQXuUIzEw0TuiSk",
  authDomain: "route2unikl.firebaseapp.com",
  projectId: "route2unikl",
  storageBucket: "route2unikl.firebasestorage.app",
  messagingSenderId: "355055657710",
  appId: "1:355055657710:web:9209898f4a3ca8864c09ff"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

//export
export { auth, db };
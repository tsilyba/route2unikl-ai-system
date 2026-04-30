# backend/core/firebase.py
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """
    Initializes the Firebase app using your downloaded service account key.
    Returns the Firestore database client so we can save and read data.
    """
    # This points to the JSON key you downloaded and placed in the backend folder
    cred = credentials.Certificate("serviceAccountKey.json")
    
    # Check if the app is already initialized to prevent errors during server reloads
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        
    db = firestore.client()
    return db
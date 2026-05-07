# backend/core/firebase.py
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """
    Initializes the Firebase app using your downloaded service account key.
    Returns the Firestore database client so we can save and read data.
    """
    cred = credentials.Certificate("serviceAccountKey.json")
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        
    db = firestore.client()
    return db
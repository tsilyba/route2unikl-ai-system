# backend/core/firebase.py
import os
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """
    Initializes the Firebase app using your downloaded service account key.
    Returns the Firestore database client so we can save and read data.
    """
    backend_dir = Path(__file__).resolve().parent.parent
    key_path = backend_dir / "serviceAccountKey.json"

    cred = credentials.Certificate(str(key_path))
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        
    db = firestore.client()
    return db
# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.firebase import initialize_firebase

# 1. Initialize the FastAPI application
app = FastAPI(
    title="Route2UniKL API",
    description="Backend for the Major Selection Support System"
)

# 2. Set up CORS so the React frontend can securely communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # Your Vite React port
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods like GET, POST, PUT, DELETE
    allow_headers=["*"], # Allows all headers
)

# 3. Connect to the Firebase database right when the server starts up
try:
    db = initialize_firebase()
    print("Firebase successfully connected!")
except Exception as e:
    print(f"Error connecting to Firebase: {e}")

# 4. Create a simple test route to verify the server is alive
@app.get("/")
def read_root():
    return {
        "status": "success", 
        "message": "Welcome to the Route2UniKL Backend! Server and Database are active."
    }
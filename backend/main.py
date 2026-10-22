# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.firebase import initialize_firebase
from routes.assessment import router as assessment_router

app = FastAPI(
    title="Route2UniKL API",
    description="Backend for the Major Selection Support System"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], # React port
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods like GET, POST, PUT, DELETE
    allow_headers=["*"], # Allows all headers
)

# Mount AI Assessment RAG Router
app.include_router(assessment_router, prefix="/api/assessment", tags=["AI Assessment"])

try:
    db = initialize_firebase()
    print("Firebase successfully connected!")
except Exception as e:
    print(f"Error connecting to Firebase: {e}")

@app.get("/")
def read_root():
    return {
        "status": "success", 
        "message": "Welcome to the Route2UniKL Backend! Server and Database are active."
    }
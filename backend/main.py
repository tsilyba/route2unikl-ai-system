# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.firebase import initialize_firebase
from routes.assessment import router as assessment_router
from routes.auth_check import router as auth_check_router
from routes.admin_users import router as admin_users_router
from routes.registration import registration_enabled, router as registration_router

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

# Mount read-only authentication / admin-authorization check endpoints
app.include_router(auth_check_router, prefix="/api", tags=["Auth"])

# Mount read-only Admin "Manage Users" endpoints (require_admin; M3A)
app.include_router(admin_users_router, prefix="/api/admin/users", tags=["Admin Users"])

# Trusted student registration (M3B-1B-P1-B2A): mounted ONLY when the backend starts in Firebase
# emulator mode, for local development and tests. In production mode the route does not exist
# (and the router itself would answer 404 outside emulator mode).
if registration_enabled():
    app.include_router(registration_router, prefix="/api/account", tags=["Account (local emulator only)"])

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
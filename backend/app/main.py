from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.patients import router as patients_router
from app.routers.users import roles_router, router as users_router

app = FastAPI(
    title="NexusCare OPD API",
    version="1.0.0",
    docs_url="/api/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(patients_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "NexusCare"}

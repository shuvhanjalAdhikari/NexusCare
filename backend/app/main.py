from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.admin import router as admin_router
from app.routers.appointments import router as appointments_router
from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.billing import router as billing_router
from app.routers.doctors import router as doctors_router
from app.routers.drugs import inventory_router, router as drugs_router
from app.routers.feedback import router as feedback_router
from app.routers.followups import (
    router as followups_router,
    visit_followups_router,
)
from app.routers.invoices import router as invoices_router
from app.routers.labs import (
    lab_tests_router,
    router as lab_orders_router,
    visit_lab_orders_router,
)
from app.routers.notifications import (
    admin_router as notifications_admin_router,
    router as notifications_router,
)
from app.routers.patients import router as patients_router
from app.routers.prescriptions import (
    router as prescriptions_router,
    visit_prescriptions_router,
)
from app.routers.queue import router as queue_router
from app.routers.referrals import router as referrals_router
from app.routers.users import roles_router, router as users_router
from app.routers.visits import router as visits_router

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
app.include_router(doctors_router)
app.include_router(appointments_router)
app.include_router(queue_router)
app.include_router(visits_router)
app.include_router(referrals_router)
app.include_router(drugs_router)
app.include_router(inventory_router)
app.include_router(prescriptions_router)
app.include_router(visit_prescriptions_router)
app.include_router(lab_tests_router)
app.include_router(lab_orders_router)
app.include_router(visit_lab_orders_router)
app.include_router(invoices_router)
app.include_router(billing_router)
app.include_router(notifications_router)
app.include_router(notifications_admin_router)
app.include_router(followups_router)
app.include_router(visit_followups_router)
app.include_router(feedback_router)
app.include_router(audit_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "NexusCare"}

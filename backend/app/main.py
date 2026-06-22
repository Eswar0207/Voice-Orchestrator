"""
FastAPI server: REST endpoints for the dashboard + the Vapi webhook handler.

Endpoints:
    GET  /api/companies                       list tenants
    GET  /api/companies/{company_id}/customers leads for a tenant
    GET  /api/customers/{customer_id}/logs     call logs for a lead
    POST /api/campaigns/{company_id}/trigger   run Dispatch flow
    POST /api/webhooks/vapi                    Vapi end-of-call-report webhook

Static frontend (built by `vite build`) is mounted at "/" when present, so a
single container can serve both API and UI on Cloud Run.
"""
import logging
import os
import uuid

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import get_settings
from app.database import CallLog, Company, Customer, SessionLocal, init_db, seed_if_empty
from app.orchestrator import run_dispatch, run_evaluation
from app.webhook_security import verify_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="Multi-Tenant Agentic Voice Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # Check database configuration
    if settings.ENVIRONMENT == "production":
        if "localhost" in settings.DATABASE_URL:
            logger.warning(
                "⚠️ CRITICAL DATABASE CONFIGURATION WARNING:\n"
                "The database URL ('DATABASE_URL') is pointing to 'localhost' in a production environment.\n"
                "This will cause database connection errors unless you are running a local database proxy inside the container.\n"
                "If you are deploying to GCP Cloud Run and using Cloud SQL, ensure that:\n"
                "  1. The Cloud Run service has the Cloud SQL connection enabled (e.g. using --add-cloudsql-instances).\n"
                "  2. The DATABASE_URL secret/env var is set to the Unix socket format:\n"
                "     postgresql+psycopg2://<db_user>:<db_pass>@/<db_name>?host=/cloudsql/<INSTANCE_CONNECTION_NAME>\n"
            )
        elif "sqlite" in settings.DATABASE_URL:
            logger.warning(
                "⚠️ DATABASE CONFIGURATION WARNING:\n"
                "The application is using a SQLite database ('DATABASE_URL') in a production environment.\n"
                "While the application will run successfully, any database changes (leads, call logs, campaigns) "
                "will be lost whenever the Cloud Run instance scales down or restarts.\n"
                "For production, please configure a persistent PostgreSQL database (GCP Cloud SQL)."
            )

    try:
        logger.info("Initializing database on startup...")
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as exc:
        logger.error(
            f"Failed to initialize database on startup. The application will continue to boot, "
            f"but database operations will fail: {exc}",
            exc_info=True
        )

    try:
        logger.info("Checking database seeding...")
        seed_if_empty()
        logger.info("Database seeding checked.")
    except Exception as exc:
        logger.error(f"Failed to seed database: {exc}", exc_info=True)


# --- Schemas -------------------------------------------------------------

class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    prompt_instructions: str

    class Config:
        from_attributes = True


class CustomerOut(BaseModel):
    id: uuid.UUID
    name: str
    phone_number: str
    status: str
    vapi_call_id: str | None = None

    class Config:
        from_attributes = True


class CallLogOut(BaseModel):
    id: uuid.UUID
    transcript: str | None = None
    summary: str | None = None
    call_metadata: dict | None = None

    class Config:
        from_attributes = True


class DispatchResponse(BaseModel):
    dispatched_count: int
    errors: list[str] = Field(default_factory=list)


# --- Dashboard endpoints ---------------------------------------------------

@app.get("/api/companies", response_model=list[CompanyOut])
def list_companies():
    db = SessionLocal()
    try:
        return db.query(Company).all()
    finally:
        db.close()


@app.get("/api/companies/{company_id}/customers", response_model=list[CustomerOut])
def list_customers(company_id: uuid.UUID):
    db = SessionLocal()
    try:
        customers = db.query(Customer).filter(Customer.company_id == company_id).all()
        return [
            CustomerOut(
                id=c.id,
                name=c.name,
                phone_number=c.phone_number,
                status=c.status.value,
                vapi_call_id=c.vapi_call_id,
            )
            for c in customers
        ]
    finally:
        db.close()


@app.get("/api/customers/{customer_id}/logs", response_model=list[CallLogOut])
def list_call_logs(customer_id: uuid.UUID):
    db = SessionLocal()
    try:
        return db.query(CallLog).filter(CallLog.customer_id == customer_id).all()
    finally:
        db.close()


def simulate_call_completion(customer_id: str, customer_name: str, customer_phone: str):
    """
    Simulates a call duration, then runs the evaluation flow in simulation mode.
    """
    import time
    time.sleep(5)
    
    from app.llm_eval import get_mock_transcript_and_eval
    from app.orchestrator import run_evaluation
    
    transcript, summary, evaluation = get_mock_transcript_and_eval(customer_name, customer_phone)
    
    run_evaluation(
        customer_id=customer_id,
        vapi_call_id=f"mock_call_{customer_id[:8]}",
        transcript=transcript,
        summary=summary,
        call_metadata={
            "duration_seconds": 45.0,
            "cost": 0.15,
            "ended_reason": "customer-hung-up"
        }
    )


@app.post("/api/campaigns/{company_id}/trigger", response_model=DispatchResponse)
def trigger_campaign(company_id: uuid.UUID, background_tasks: BackgroundTasks):
    result = run_dispatch(str(company_id))
    
    if settings.SIMULATION_MODE:
        dispatched_customers = result.get("dispatched_customers") or []
        for customer in dispatched_customers:
            background_tasks.add_task(
                simulate_call_completion,
                customer_id=customer["id"],
                customer_name=customer["name"],
                customer_phone=customer.get("phone", ""),
            )
            
    return DispatchResponse(
        dispatched_count=result.get("dispatched_count", 0),
        errors=result.get("errors", []),
    )


@app.post("/api/campaigns/{company_id}/reset")
def reset_campaign(company_id: uuid.UUID):
    db = SessionLocal()
    try:
        from app.database import LeadStatus
        
        # 1. Fetch all customers belonging to this specific company
        customers = db.query(Customer).filter(Customer.company_id == company_id).all()
        
        for customer in customers:
            # 2. Reset every customer to PENDING (No hardcoded names!)
            customer.status = LeadStatus.PENDING
            customer.vapi_call_id = None
            
            # 3. Clean up the logs for this customer to clear the UI
            db.query(CallLog).filter(CallLog.customer_id == customer.id).delete()
            
        db.commit()
        return {"status": "ok", "message": f"Reset {len(customers)} leads successfully."}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()


# --- Webhook ---------------------------------------------------------------

@app.post("/api/webhooks/vapi")
async def vapi_webhook(request: Request):
    raw_body = await request.body()
    signature_header = request.headers.get("x-vapi-signature")

    if not verify_signature(raw_body, signature_header):
        logger.warning("Rejected webhook: invalid or missing signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    message = payload.get("message", payload)  # Vapi nests payloads under "message"

    if message.get("type") != "end-of-call-report":
        # Structurally valid but not the event we act on; acknowledge and ignore.
        return {"status": "ignored", "reason": "not an end-of-call-report event"}

    metadata = message.get("call", {}).get("metadata") or message.get("metadata") or {}
    customer_id = metadata.get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="Missing metadata.customer_id in webhook payload")

    transcript = message.get("transcript", "")
    summary = message.get("summary")
    vapi_call_id = message.get("call", {}).get("id")
    call_meta = {
        "duration_seconds": message.get("durationSeconds"),
        "cost": message.get("cost"),
        "ended_reason": message.get("endedReason"),
    }

    run_evaluation(
        customer_id=customer_id,
        vapi_call_id=vapi_call_id,
        transcript=transcript,
        summary=summary,
        call_metadata=call_meta,
    )

    return {"status": "processed"}


# --- Health check -----------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


# --- Static frontend (built assets) -----------------------------------------

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")

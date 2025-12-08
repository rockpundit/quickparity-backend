import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
from backend.connectors.simulated import (
    SimulatedStripeClient, SimulatedQBOClient, SimulatedSquareClient, 
    SimulatedShopifyClient, SimulatedPayPalClient
)
from backend.services.mock_generator import MockDataGenerator

import os

logger = logging.getLogger("ReconciliationControlPlane")

app = FastAPI(title="Reconciliation Control Plane API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Reconciliation Control Plane API is operational."}

# Import and include routers here later
# Import and include routers here later
from backend.api.routes import router as api_router
from backend.api.auth import router as auth_router
from backend.api.settings import router as settings_router

app.include_router(api_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(settings_router, prefix="/api")

# Startup Event for Scheduler
from backend.services.scheduler import SchedulerService
from backend.services.tenant import TenantManager
import asyncio

@app.on_event("startup")
async def start_scheduler():
    # In a real production app with multiple workers, this would be duplicated.
    # Typically scheduler is a separate process. for this demo, we run it in-app.
    # To avoid multiple schedulers if multiple workers, we can rely on an environment flag or run separate command.
    # But user asked for periodic sync.
    # We will just start it here.
    tm = TenantManager()
    scheduler = SchedulerService(tm)
    task = asyncio.create_task(scheduler.start())
    # Store reference to avoid GC?
    app.state.scheduler_task = task



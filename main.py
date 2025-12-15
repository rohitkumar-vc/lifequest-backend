from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from routes import auth, tasks, shop, analytics
from core.config import settings
from core.scheduler import start_scheduler, run_daily_maintenance

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_scheduler()
    # Run maintenance check immediately on startup
    await run_daily_maintenance()
    yield
    # Shutdown
    pass

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# CORS
origins = [
    settings.FRONTEND_URL,
    "http://127.0.0.1:5173", # Keep local fallback just in case
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ...
# Routers
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(shop.router)
app.include_router(analytics.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to LifeQuest API"}

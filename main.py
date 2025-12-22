from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from routes import auth, tasks, shop, analytics, habits, todos
from core.config import settings


app = FastAPI(title=settings.APP_NAME)

print(settings.FRONTEND_URL)

# CORS
origins = [
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000", # Common alternative
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
app.include_router(habits.router)
app.include_router(todos.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to LifeQuest API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

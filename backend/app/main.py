from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.db.database import init_db

app = FastAPI(title="RingWatch API", version="1.0.0")

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return {"service": "RingWatch", "docs": "/docs"}

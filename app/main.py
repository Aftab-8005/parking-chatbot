import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin_routes import router as admin_router
from app.api.routes import router as chat_router
from app.config import settings
from app.database.session import init_db

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(chat_router)
app.include_router(admin_router)


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "env": settings.app_env}

from fastapi import FastAPI

from app.api.admin_routes import router as admin_router
from app.api.routes import router
from app.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(router)
app.include_router(admin_router)


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "env": settings.app_env}

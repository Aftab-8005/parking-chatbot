from fastapi import FastAPI

from app.api.routes import router
from app.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "env": settings.app_env}

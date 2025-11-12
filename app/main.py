from fastapi import FastAPI
from .auth import auth_router
from .registration import registration_router
from .usage import usage_router
from .generation import generation_router

app = FastAPI()
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(registration_router, prefix="/api", tags=["registration"])
app.include_router(usage_router, prefix="/api", tags=["usage"])
app.include_router(generation_router, prefix="/api", tags=["generation"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True, log_config="logging.conf")f
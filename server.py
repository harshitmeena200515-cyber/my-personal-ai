import platform
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from core.logging import setup_logging, logger

setup_logging(debug=settings.DEBUG)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous Personal AI Platform with Hybrid Intelligence & Local Hardware Control",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "router_mode": settings.ROUTER_MODE,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "host": settings.HOST,
        "port": settings.PORT,
    }


@app.get("/api/v1/system/info")
async def system_info():
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "gpu": "NVIDIA GeForce RTX 3050 Laptop GPU (4GB VRAM)",
        "ram": "16 GB",
    }


@app.get("/api/v1/models/status")
async def models_status():
    return {
        "router_mode": settings.ROUTER_MODE,
        "default_local": settings.DEFAULT_LOCAL_MODEL,
        "default_cloud": settings.DEFAULT_CLOUD_MODEL,
        "ollama_endpoint": settings.OLLAMA_BASE_URL,
        "cloud_providers": {
            "gemini": bool(settings.GEMINI_API_KEY),
            "groq": bool(settings.GROQ_API_KEY),
            "openai": bool(settings.OPENAI_API_KEY),
            "anthropic": bool(settings.ANTHROPIC_API_KEY),
        },
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("starting_server", host=settings.HOST, port=settings.PORT)
    uvicorn.run("server:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)

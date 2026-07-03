"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.db import Base, engine
from routes import auth, dashboard, rules, traffic


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup for local dev (replaced by Alembic migrations later)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Firewall AI — Layer 1 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(rules.router)
app.include_router(traffic.router)
app.include_router(dashboard.router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


if __name__ == "__main__":
    # Run via `python main.py`, not the `uvicorn` CLI: uvicorn.run() hardcodes
    # ProactorEventLoop on Windows, which psycopg's async mode cannot use. Driving
    # Server.serve() through asyncio.run(loop_factory=...) forces SelectorEventLoop.
    import asyncio

    import uvicorn

    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)

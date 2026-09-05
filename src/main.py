import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

from mcp_server import __version__, mcp, mcp_http_app
from routes import app_router
from utils.env_load_util import EnvLoadUtil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ],
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Mounting disables the MCP app's built-in lifespan, so the host app
    # must run the session manager itself.
    async with mcp.session_manager.run():
        yield

app = FastAPI(lifespan=lifespan)
app.include_router(app_router, prefix="/router", tags=["kmb_router"])
# MCP endpoint is exactly /mcp (mount prefix + streamable_http_path="/").
app.mount("/mcp", mcp_http_app)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": __version__}

if __name__ == "__main__":
    uvicorn.run("main:app", host=EnvLoadUtil.load_env("APPLICATION_SERVER_HOST", "127.0.0.1"),
                port=int(EnvLoadUtil.load_env("APPLICATION_SERVER_PORT", 8000)), reload=True)

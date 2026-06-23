from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.auth import require_token
from app.config import Settings, get_settings
from app.cue_engine import CueEngine
from app.db import Database
from app.detector import ObjectionDetector
from app.hub import CueHub
from app.models import CueCard, KnowledgeItem, SessionCreate, SessionInfo, TranscriptEvent
from app.stt import SpeechToTextStreamer, build_stt_streamer

logger = structlog.get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()
db = Database(settings.database_path)
hub = CueHub()
detector = ObjectionDetector(settings)
cue_engine = CueEngine(db, settings)
stt_streamer: SpeechToTextStreamer = build_stt_streamer(settings)
templates = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")), autoescape=select_autoescape()
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize resources at startup."""

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )
    await db.init()
    yield


app = FastAPI(
    title="AI Live Sales Objection Killer Agent",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check for container platforms."""

    return {"status": "ok"}


@app.post("/api/knowledge", dependencies=[Depends(require_token)])
async def upsert_knowledge(item: KnowledgeItem) -> dict[str, str]:
    """Add or update an internal sales knowledge item."""

    await db.upsert_knowledge_item(item)
    return {"status": "ok", "id": item.id}


@app.post("/api/sessions", dependencies=[Depends(require_token)])
async def create_session(payload: SessionCreate, request: Request) -> SessionInfo:
    """Create a sales-call monitoring session."""

    session_id = str(uuid4())
    hub.bind_session(session_id=session_id, rep_id=payload.rep_id)
    base_url = str(request.base_url).rstrip("/")
    ws_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
    return SessionInfo(
        session_id=session_id,
        rep_id=payload.rep_id,
        audio_ws_url=f"{ws_base}/ws/audio/{session_id}?token={settings.rep_shared_token.get_secret_value()}",
        dashboard_url=f"{base_url}/dashboard/{payload.rep_id}?token={settings.rep_shared_token.get_secret_value()}",
    )


@app.get("/capture/{session_id}", response_class=HTMLResponse, dependencies=[Depends(require_token)])
async def capture_page(session_id: str, request: Request) -> HTMLResponse:
    """Browser audio capture page for Zoom/Meet/Teams tab audio."""

    template = templates.get_template("capture.html")
    ws_url = str(request.base_url).rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
    html = template.render(session_id=session_id, ws_url=ws_url, token=settings.rep_shared_token.get_secret_value())
    return HTMLResponse(html)


@app.get("/dashboard/{rep_id}", response_class=HTMLResponse, dependencies=[Depends(require_token)])
async def dashboard(rep_id: str, request: Request) -> HTMLResponse:
    """Private secondary-monitor dashboard for sales rep cue cards."""

    template = templates.get_template("dashboard.html")
    ws_url = str(request.base_url).rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
    html = template.render(rep_id=rep_id, ws_url=ws_url, token=settings.rep_shared_token.get_secret_value())
    return HTMLResponse(html)


@app.websocket("/ws/dashboard/{rep_id}")
async def dashboard_ws(rep_id: str, websocket: WebSocket) -> None:
    """Cue-card websocket consumed by private rep dashboard."""

    if not _valid_ws_token(websocket):
        await websocket.close(code=1008)
        return
    await hub.connect(rep_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(rep_id, websocket)


@app.websocket("/ws/audio/{session_id}")
async def audio_ws(session_id: str, websocket: WebSocket) -> None:
    """Receive browser call audio and stream it to realtime STT."""

    if not _valid_ws_token(websocket):
        await websocket.close(code=1008)
        return

    async def on_transcript(event: TranscriptEvent) -> None:
        started = time.perf_counter()
        signal = detector.inspect(event)
        if not signal:
            return
        card = await cue_engine.build_card(signal, started_at=started)
        await hub.publish_card(card)
        logger.info(
            "cue_card_published",
            session_id=session_id,
            objection_type=str(card.objection_type),
            latency_ms=card.latency_ms,
        )

    try:
        await stt_streamer.bridge(session_id=session_id, websocket=websocket, on_transcript=on_transcript)
    except WebSocketDisconnect:
        logger.info("audio_ws_disconnected", session_id=session_id)


@app.post("/api/test-cue/{session_id}", dependencies=[Depends(require_token)])
async def test_cue(session_id: str) -> CueCard:
    """Developer endpoint to simulate a pricing objection without live audio."""

    event = TranscriptEvent(
        session_id=session_id,
        text="This is too expensive. HubSpot seems cheaper and our budget is tight.",
        is_final=True,
    )
    started = time.perf_counter()
    signal = detector.inspect(event)
    if signal is None:
        raise RuntimeError("test phrase did not trigger detector")
    card = await cue_engine.build_card(signal, started_at=started)
    await hub.publish_card(card)
    return card


def _valid_ws_token(websocket: WebSocket) -> bool:
    expected = settings.rep_shared_token.get_secret_value()
    provided = websocket.query_params.get("token", "")
    return bool(expected and provided == expected)


async def main() -> None:
    """Run the ASGI app with uvicorn."""

    import uvicorn

    runtime_settings: Settings = get_settings()
    config = uvicorn.Config(
        "app.main:app",
        host=runtime_settings.app_host,
        port=runtime_settings.app_port,
        reload=runtime_settings.app_env == "development",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

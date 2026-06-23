from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Protocol

import aiohttp
import structlog
from fastapi import WebSocket
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config import Settings
from app.models import TranscriptEvent

logger = structlog.get_logger(__name__)
TranscriptCallback = Callable[[TranscriptEvent], Awaitable[None]]


class SpeechToTextStreamer(Protocol):
    """Realtime STT bridge interface."""

    async def bridge(self, session_id: str, websocket: WebSocket, on_transcript: TranscriptCallback) -> None:
        """Bridge browser audio websocket to an STT provider."""


class MockSpeechToTextStreamer:
    """Local/test STT mode: send text websocket messages instead of audio."""

    async def bridge(self, session_id: str, websocket: WebSocket, on_transcript: TranscriptCallback) -> None:
        await websocket.accept()
        while True:
            message = await websocket.receive()
            if "text" in message and message["text"]:
                await on_transcript(
                    TranscriptEvent(session_id=session_id, text=message["text"], is_final=True)
                )
            if message.get("type") == "websocket.disconnect":
                break


class DeepgramSpeechToTextStreamer:
    """Deepgram realtime bridge using browser MediaRecorder webm/opus chunks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def bridge(self, session_id: str, websocket: WebSocket, on_transcript: TranscriptCallback) -> None:
        await websocket.accept()
        api_key = self.settings.deepgram_api_key.get_secret_value() if self.settings.deepgram_api_key else ""
        if not api_key:
            await websocket.send_json({"type": "error", "message": "DEEPGRAM_API_KEY is missing"})
            await websocket.close(code=1011)
            return

        await self._run_deepgram_bridge(session_id, websocket, on_transcript, api_key)

    @retry(
        retry=retry_if_exception_type((aiohttp.ClientConnectionError, asyncio.TimeoutError)),
        wait=wait_exponential_jitter(initial=0.25, max=2.0),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _run_deepgram_bridge(
        self,
        session_id: str,
        websocket: WebSocket,
        on_transcript: TranscriptCallback,
        api_key: str,
    ) -> None:
        query = {
            "model": self.settings.deepgram_model,
            "language": self.settings.deepgram_language,
            "smart_format": "true",
            "interim_results": "true",
            "utterance_end_ms": "900",
            "vad_events": "true",
            # Browser client sends audio/webm; Deepgram auto-detects container/codec.
            "encoding": "opus",
            "sample_rate": "48000",
            "channels": "1",
        }
        headers = {"Authorization": f"Token {api_key}"}
        timeout = aiohttp.ClientTimeout(total=None, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                "wss://api.deepgram.com/v1/listen",
                headers=headers,
                params=query,
                heartbeat=20,
                max_msg_size=8 * 1024 * 1024,
            ) as dg_ws:
                logger.info("deepgram_connected", session_id=session_id)
                receive_task = asyncio.create_task(
                    self._receive_browser_audio(websocket=websocket, dg_ws=dg_ws)
                )
                transcript_task = asyncio.create_task(
                    self._receive_transcripts(
                        session_id=session_id, dg_ws=dg_ws, on_transcript=on_transcript
                    )
                )
                done, pending = await asyncio.wait(
                    {receive_task, transcript_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in pending:
                    with suppress(asyncio.CancelledError):
                        await task
                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc

    async def _receive_browser_audio(self, websocket: WebSocket, dg_ws: aiohttp.ClientWebSocketResponse) -> None:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                await dg_ws.close()
                return
            if data := message.get("bytes"):
                await dg_ws.send_bytes(data)
            elif text := message.get("text"):
                if text == "stop":
                    await dg_ws.close()
                    return

    async def _receive_transcripts(
        self,
        session_id: str,
        dg_ws: aiohttp.ClientWebSocketResponse,
        on_transcript: TranscriptCallback,
    ) -> None:
        async for message in dg_ws:
            if message.type == aiohttp.WSMsgType.TEXT:
                payload = json.loads(message.data)
                transcript = self._parse_deepgram_payload(session_id, payload)
                if transcript:
                    await on_transcript(transcript)
            elif message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                return

    @staticmethod
    def _parse_deepgram_payload(session_id: str, payload: dict[str, object]) -> TranscriptEvent | None:
        channel = payload.get("channel")
        if not isinstance(channel, dict):
            return None
        alternatives = channel.get("alternatives")
        if not isinstance(alternatives, list) or not alternatives:
            return None
        first = alternatives[0]
        if not isinstance(first, dict):
            return None
        text = str(first.get("transcript") or "").strip()
        if not text:
            return None
        return TranscriptEvent(
            session_id=session_id,
            text=text,
            is_final=bool(payload.get("is_final", False)),
        )


def build_stt_streamer(settings: Settings) -> SpeechToTextStreamer:
    """Create configured STT streamer."""

    if settings.stt_provider == "mock":
        return MockSpeechToTextStreamer()
    return DeepgramSpeechToTextStreamer(settings)

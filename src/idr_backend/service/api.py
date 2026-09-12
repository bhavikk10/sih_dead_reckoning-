"""FastAPI/WebSocket application for live deterministic IDR sessions."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from ..sensors.types import GnssFix
from .models import (
    ErrorStreamEvent,
    EstimateEnvelope,
    EstimateStreamEvent,
    GnssFixPayload,
    GnssStreamEvent,
    IngestResponse,
    NavigationSessionCreateRequest,
    NavigationSessionResponse,
    PublishedEstimate,
    RawImuPayload,
    ImuStreamEvent,
)
from .runtime import (
    NavigationSession,
    NavigationSessionRegistry,
    PipelineFactory,
    PublicEstimate,
    ReviewedRuntimeArtifacts,
    build_reviewed_navigation_pipeline,
    raw_imu_from_payload,
)


SessionId = Annotated[str, Path(min_length=1, max_length=128)]
ClientStreamEvent = Annotated[
    GnssStreamEvent | ImuStreamEvent,
    "Pydantic validates the explicit type literal in each WebSocket envelope.",
]
_CLIENT_STREAM_EVENT = TypeAdapter(ClientStreamEvent)


def create_app(
    *,
    pipeline_factory: PipelineFactory | None = None,
) -> FastAPI:
    """Create a service app, allowing tests to inject a no-artifact pipeline."""

    factory = pipeline_factory or (
        lambda: build_reviewed_navigation_pipeline(ReviewedRuntimeArtifacts.defaults())
    )
    registry = NavigationSessionRegistry(factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        registry.stop_all()

    app = FastAPI(
        title="IDR navigation service",
        version="v1",
        description=(
            "Session-scoped deterministic GNSS/IMU fusion. Road context remains disabled."
        ),
        lifespan=lifespan,
    )
    app.state.navigation_sessions = registry

    @app.get("/health")
    def health() -> dict[str, Literal["ok"] | bool]:
        return {"status": "ok", "roadContextEnabled": False}

    @app.post(
        "/v1/navigation-sessions",
        response_model=NavigationSessionResponse,
        response_model_by_alias=True,
    )
    def create_navigation_session(
        request: NavigationSessionCreateRequest,
    ) -> NavigationSessionResponse:
        session = registry.create(
            source_id=request.source_id,
            receiver_id=request.receiver_id,
        )
        return NavigationSessionResponse(
            session_id=session.session_id,
            websocket_path=f"/v1/navigation-sessions/{session.session_id}/stream",
        )

    @app.post(
        "/v1/navigation-sessions/{session_id}/gnss",
        response_model=IngestResponse,
        response_model_by_alias=True,
    )
    def submit_gnss(
        session_id: SessionId,
        payload: GnssFixPayload,
    ) -> IngestResponse:
        session = _session_or_404(registry, session_id)
        try:
            _push_gnss(session, payload)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return IngestResponse(estimate=_published_or_none(session.latest_estimate))

    @app.post(
        "/v1/navigation-sessions/{session_id}/imu",
        response_model=IngestResponse,
        response_model_by_alias=True,
    )
    def submit_imu(
        session_id: SessionId,
        payload: RawImuPayload,
    ) -> IngestResponse:
        session = _session_or_404(registry, session_id)
        try:
            estimate = _push_imu(session, payload)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return IngestResponse(estimate=_published_or_none(estimate))

    @app.get(
        "/v1/navigation-sessions/{session_id}/estimate",
        response_model=EstimateEnvelope,
        response_model_by_alias=True,
    )
    def get_estimate(session_id: SessionId) -> EstimateEnvelope:
        session = _session_or_404(registry, session_id)
        return EstimateEnvelope(estimate=_published_or_none(session.latest_estimate))

    @app.delete("/v1/navigation-sessions/{session_id}", status_code=204)
    def delete_navigation_session(session_id: SessionId) -> None:
        try:
            registry.delete(session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.websocket("/v1/navigation-sessions/{session_id}/stream")
    async def stream_navigation(session_id: str, websocket: WebSocket) -> None:
        try:
            session = registry.get(session_id)
        except KeyError:
            await websocket.close(code=4404, reason="Unknown navigation session.")
            return

        await websocket.accept()
        try:
            while True:
                try:
                    event = _CLIENT_STREAM_EVENT.validate_python(
                        await websocket.receive_json()
                    )
                    estimate = await asyncio.to_thread(_push_stream_event, session, event)
                    if estimate is not None:
                        await websocket.send_json(
                            EstimateStreamEvent(
                                estimate=_published_or_none(estimate)  # type: ignore[arg-type]
                            ).model_dump(by_alias=True)
                        )
                except ValidationError as error:
                    await _send_stream_error(websocket, "invalid_payload", str(error))
                except ValueError as error:
                    await _send_stream_error(websocket, "rejected_event", str(error))
        except WebSocketDisconnect:
            return

    return app


def _session_or_404(registry: NavigationSessionRegistry, session_id: str) -> NavigationSession:
    try:
        return registry.get(session_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _push_stream_event(
    session: NavigationSession,
    event: GnssStreamEvent | ImuStreamEvent,
) -> PublicEstimate | None:
    if isinstance(event, GnssStreamEvent):
        _push_gnss(session, event.fix)
        return None
    return _push_imu(session, event.sample)


def _push_gnss(session: NavigationSession, payload: GnssFixPayload) -> None:
    session.push_gnss(
        GnssFix(
            timestamp_ns=payload.timestamp_ns,
            receiver_id=payload.receiver_id,
            latitude_deg=payload.latitude_deg,
            longitude_deg=payload.longitude_deg,
            altitude_m=payload.altitude_m,
            horizontal_accuracy_m=payload.horizontal_accuracy_m,
            vertical_accuracy_m=payload.vertical_accuracy_m,
            speed_mps=payload.speed_mps,
            speed_accuracy_mps=payload.speed_accuracy_mps,
            course_over_ground_rad=payload.course_over_ground_rad,
            course_accuracy_rad=payload.course_accuracy_rad,
        )
    )


def _push_imu(session: NavigationSession, payload: RawImuPayload) -> PublicEstimate | None:
    return session.push_imu(
        raw_imu_from_payload(
            timestamp_ns=payload.timestamp_ns,
            source_id=payload.source_id,
            kind=payload.kind,
            value=payload.value,
            unit=payload.unit,
            frame=payload.frame,
            vendor_accuracy=payload.vendor_accuracy,
        )
    )


def _published_or_none(value: PublicEstimate | None) -> PublishedEstimate | None:
    return None if value is None else PublishedEstimate(**asdict(value))


async def _send_stream_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json(
        ErrorStreamEvent(code=code, message=message).model_dump(by_alias=True)
    )

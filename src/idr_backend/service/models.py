"""Versioned JSON models for the mobile-to-IDR service boundary."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


def _camel_case(value: str) -> str:
    """Serialize Python contract names as conventional mobile JSON keys."""

    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    """Strict camel-case JSON base shared by every public service message."""

    model_config = ConfigDict(
        alias_generator=_camel_case,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
        allow_inf_nan=False,
    )


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Vector3 = tuple[FiniteFloat, FiniteFloat, FiniteFloat]


class NavigationSessionCreateRequest(ApiModel):
    """Immutable identifiers selected when a phone navigation session begins."""

    source_id: str = Field(default="phone-primary", min_length=1, max_length=128)
    receiver_id: str = Field(default="phone-primary", min_length=1, max_length=128)


class NavigationSessionResponse(ApiModel):
    """Safe session information returned immediately after creation."""

    session_id: str
    websocket_path: str
    road_context_enabled: Literal[False] = False


class GnssFixPayload(ApiModel):
    """One phone GNSS observation, retaining absent quality fields as null."""

    timestamp_ns: int = Field(ge=0)
    receiver_id: str = Field(min_length=1, max_length=128)
    latitude_deg: FiniteFloat = Field(ge=-90.0, le=90.0)
    longitude_deg: FiniteFloat = Field(ge=-180.0, le=180.0)
    altitude_m: FiniteFloat | None = None
    horizontal_accuracy_m: FiniteFloat | None = Field(default=None, gt=0.0)
    vertical_accuracy_m: FiniteFloat | None = Field(default=None, gt=0.0)
    speed_mps: FiniteFloat | None = Field(default=None, ge=0.0)
    speed_accuracy_mps: FiniteFloat | None = Field(default=None, gt=0.0)
    course_over_ground_rad: FiniteFloat | None = None
    course_accuracy_rad: FiniteFloat | None = Field(default=None, gt=0.0, le=3.141592653589793)


class RawImuPayload(ApiModel):
    """One unmodified phone accelerometer or gyroscope callback."""

    timestamp_ns: int = Field(ge=0)
    source: Literal["phone"] = "phone"
    source_id: str = Field(min_length=1, max_length=128)
    kind: Literal["accelerometer", "gyroscope"]
    value: Vector3
    unit: Literal["m/s^2", "rad/s"]
    frame: Literal["sensor"]
    vendor_accuracy: int | None = None


class GnssStreamEvent(ApiModel):
    """WebSocket envelope carrying one GNSS callback."""

    type: Literal["gnss"]
    fix: GnssFixPayload


class ImuStreamEvent(ApiModel):
    """WebSocket envelope carrying one raw IMU callback."""

    type: Literal["imu"]
    sample: RawImuPayload


class PublishedEstimate(ApiModel):
    """Map-ready public projection of a committed backend EKF estimate."""

    timestamp_ns: int
    latitude_deg: FiniteFloat
    longitude_deg: FiniteFloat
    altitude_m: FiniteFloat
    speed_mps: FiniteFloat
    heading_deg: FiniteFloat
    horizontal_sigma_m: FiniteFloat
    vertical_sigma_m: FiniteFloat
    mode: Literal["gnss_aided", "dead_reckoning", "recovery"]
    is_dead_reckoning: bool
    map_match_confidence: FiniteFloat | None = None


class EstimateEnvelope(ApiModel):
    """HTTP representation of a session's most recently committed estimate."""

    estimate: PublishedEstimate | None


class IngestResponse(ApiModel):
    """Acknowledgement without echoing sensitive raw sensor/location values."""

    accepted: bool = True
    estimate: PublishedEstimate | None


class EstimateStreamEvent(ApiModel):
    """WebSocket event emitted only after a new EKF state is committed."""

    type: Literal["estimate"] = "estimate"
    estimate: PublishedEstimate


class ErrorStreamEvent(ApiModel):
    """Recoverable WebSocket validation/processing error."""

    type: Literal["error"] = "error"
    code: str
    message: str

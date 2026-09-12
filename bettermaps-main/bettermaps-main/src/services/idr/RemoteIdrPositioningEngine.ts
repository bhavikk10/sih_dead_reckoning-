/**
 * RemoteIdrPositioningEngine
 *
 * Keeps BetterMaps as the sensor/UI client while the reviewed Python IDR
 * runtime owns calibration, selected ONNX velocity inference, uncertainty,
 * and the 15-state ESKF.  It intentionally sends raw phone-frame IMU axes;
 * it must never imitate the backend's vehicle-frame calibration on-device.
 */

import { ImuSample } from "../../core/types/imu";
import { NavLocation } from "../../core/types/location";
import {
  IPositioningEngine,
  PositionEstimate,
  PositionEstimateListener,
  PositioningStatus,
  PositioningStatusListener,
} from "../../core/types/positioning";

type BackendGnssPayload = {
  timestampNs: number;
  receiverId: string;
  latitudeDeg: number;
  longitudeDeg: number;
  altitudeM: number | null;
  horizontalAccuracyM: number | null;
  verticalAccuracyM: number | null;
  speedMps: number | null;
  speedAccuracyMps: null;
  courseOverGroundRad: number | null;
  courseAccuracyRad: null;
};

type BackendImuPayload = {
  timestampNs: number;
  source: "phone";
  sourceId: string;
  kind: "accelerometer" | "gyroscope";
  value: [number, number, number];
  unit: "m/s^2" | "rad/s";
  frame: "sensor";
  vendorAccuracy: null;
};

type ClientEvent =
  | { type: "gnss"; fix: BackendGnssPayload }
  | { type: "imu"; sample: BackendImuPayload };

type BackendEstimate = {
  timestampNs: number;
  latitudeDeg: number;
  longitudeDeg: number;
  altitudeM: number;
  speedMps: number;
  headingDeg: number;
  horizontalSigmaM: number;
  verticalSigmaM: number;
  mode: "gnss_aided" | "dead_reckoning" | "recovery";
  isDeadReckoning: boolean;
  mapMatchConfidence: number | null;
};

type ServerEvent =
  | { type: "estimate"; estimate: BackendEstimate }
  | { type: "error"; code: string; message: string };

type EnvironmentWithProcess = typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
};

const MAX_PENDING_EVENTS = 512;

/**
 * Returns a validated configured backend URL, or null to retain the existing
 * entirely on-device BetterMaps positioning stack.
 */
export function configuredIdrBackendUrl(): string | null {
  const value = (globalThis as EnvironmentWithProcess).process?.env
    ?.EXPO_PUBLIC_IDR_BACKEND_URL?.trim();
  if (!value) return null;

  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.toString().replace(/\/$/, "");
  } catch {
    console.warn("[IDR backend] Ignoring malformed EXPO_PUBLIC_IDR_BACKEND_URL.");
    return null;
  }
}

/**
 * Marker used by NavigationManager to avoid processing synchronous placeholder
 * returns before an asynchronous server estimate has arrived.
 */
export interface RemoteBackendPositioningEngine extends IPositioningEngine {
  readonly usesBackendTransport: true;
  startRemoteSession(): Promise<void>;
  disposeRemoteSession(): Promise<void>;
}

export function isRemoteBackendPositioningEngine(
  engine: IPositioningEngine,
): engine is RemoteBackendPositioningEngine {
  return (engine as Partial<RemoteBackendPositioningEngine>).usesBackendTransport === true;
}

export class RemoteIdrPositioningEngine
  implements RemoteBackendPositioningEngine
{
  public readonly usesBackendTransport = true as const;

  private status: PositioningStatus = "NO_POSITION";
  private currentEstimate = this.emptyEstimate();
  private readonly estimateListeners = new Set<PositionEstimateListener>();
  private readonly statusListeners = new Set<PositioningStatusListener>();
  private readonly clock = new SessionClock();
  private readonly outbound: ClientEvent[] = [];

  private socket: WebSocket | null = null;
  private sessionId: string | null = null;
  private opening: Promise<void> | null = null;
  private disposed = false;
  private lastGnssFixTimestampMs = 0;

  public constructor(
    private readonly baseUrl: string,
    private readonly sourceId = "phone-primary",
    private readonly receiverId = "phone-primary",
  ) {}

  public async startRemoteSession(): Promise<void> {
    if (this.socket?.readyState === WebSocket.OPEN || this.opening) {
      return this.opening ?? Promise.resolve();
    }
    this.disposed = false;
    this.opening = this.openSession();
    try {
      await this.opening;
    } finally {
      this.opening = null;
    }
  }

  public async disposeRemoteSession(): Promise<void> {
    this.disposed = true;
    const socket = this.socket;
    this.socket = null;
    if (socket && socket.readyState === WebSocket.OPEN) socket.close();

    const sessionId = this.sessionId;
    this.sessionId = null;
    this.outbound.length = 0;
    this.clock.reset();
    if (sessionId) {
      try {
        await fetch(`${this.baseUrl}/v1/navigation-sessions/${sessionId}`, {
          method: "DELETE",
        });
      } catch {
        // The server owns an independent timeout/cleanup policy. Do not retry
        // a deleted drive with stale callbacks on the next app session.
      }
    }
  }

  public processGnss(sample: NavLocation): PositionEstimate {
    this.lastGnssFixTimestampMs = sample.timestamp;
    this.enqueue({
      type: "gnss",
      fix: {
        timestampNs: this.clock.toSessionNs(sample.timestamp),
        receiverId: this.receiverId,
        latitudeDeg: sample.latitude,
        longitudeDeg: sample.longitude,
        altitudeM: sample.altitude ?? null,
        horizontalAccuracyM: sample.accuracy ?? null,
        verticalAccuracyM: sample.verticalAccuracy ?? sample.altitudeAccuracy ?? null,
        speedMps: sample.speed ?? null,
        // expo-location does not expose receiver speed/course uncertainty.
        // Preserve absence rather than presenting guessed values as sensor facts.
        speedAccuracyMps: null,
        courseOverGroundRad:
          sample.heading === null || sample.heading === undefined
            ? null
            : (sample.heading * Math.PI) / 180,
        courseAccuracyRad: null,
      },
    });
    return this.currentEstimate;
  }

  public processImu(sample: ImuSample): PositionEstimate | null {
    const timestampNs = this.clock.toSessionNs(sample.timestamp);
    this.enqueue({
      type: "imu",
      sample: {
        timestampNs,
        source: "phone",
        sourceId: this.sourceId,
        kind: "accelerometer",
        value: [sample.accel.x, sample.accel.y, sample.accel.z],
        unit: "m/s^2",
        frame: "sensor",
        vendorAccuracy: null,
      },
    });
    this.enqueue({
      type: "imu",
      sample: {
        timestampNs,
        source: "phone",
        sourceId: this.sourceId,
        kind: "gyroscope",
        value: [sample.gyro.x, sample.gyro.y, sample.gyro.z],
        unit: "rad/s",
        frame: "sensor",
        vendorAccuracy: null,
      },
    });
    return null;
  }

  public onGnssBlocked(): PositionEstimate {
    this.status = "GNSS_BLOCKED_SIMULATED";
    this.notifyStatus();
    return this.currentEstimate;
  }

  public getCurrentEstimate(): PositionEstimate {
    return this.currentEstimate;
  }

  public getStatus(): PositioningStatus {
    return this.status;
  }

  public getLastGnssFixTimestampMs(): number {
    return this.lastGnssFixTimestampMs;
  }

  public addEstimateListener(listener: PositionEstimateListener): () => void {
    this.estimateListeners.add(listener);
    listener(this.currentEstimate);
    return () => this.estimateListeners.delete(listener);
  }

  public addStatusListener(listener: PositioningStatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  public reset(): void {
    void this.disposeRemoteSession().then(() => this.startRemoteSession());
    this.status = "NO_POSITION";
    this.currentEstimate = this.emptyEstimate();
    this.notifyEstimate();
    this.notifyStatus();
  }

  private async openSession(): Promise<void> {
    const response = await fetch(`${this.baseUrl}/v1/navigation-sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sourceId: this.sourceId, receiverId: this.receiverId }),
    });
    if (!response.ok) {
      this.fail(`Session creation failed with HTTP ${response.status}.`);
      return;
    }
    const created = (await response.json()) as {
      sessionId?: unknown;
      websocketPath?: unknown;
    };
    if (typeof created.sessionId !== "string" || typeof created.websocketPath !== "string") {
      this.fail("Backend returned an invalid session response.");
      return;
    }
    this.sessionId = created.sessionId;
    await this.connectSocket(created.websocketPath);
  }

  private async connectSocket(path: string): Promise<void> {
    const socketUrl = `${toWebSocketBaseUrl(this.baseUrl)}${path}`;
    await new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(socketUrl);
      this.socket = socket;
      socket.onopen = () => {
        this.flushOutbound();
        resolve();
      };
      socket.onmessage = (event) => this.handleServerEvent(event.data);
      socket.onerror = () => reject(new Error("IDR backend WebSocket connection failed."));
      socket.onclose = () => {
        if (!this.disposed) this.fail("IDR backend connection closed.");
      };
    }).catch((error: unknown) => {
      this.fail(error instanceof Error ? error.message : String(error));
    });
  }

  private enqueue(event: ClientEvent): void {
    if (this.disposed) return;
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(event));
      return;
    }
    if (this.outbound.length >= MAX_PENDING_EVENTS) {
      this.fail("IDR backend queue limit reached; start a new navigation session.");
      return;
    }
    this.outbound.push(event);
    void this.startRemoteSession();
  }

  private flushOutbound(): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    while (this.outbound.length > 0) {
      this.socket.send(JSON.stringify(this.outbound.shift()!));
    }
  }

  private handleServerEvent(data: unknown): void {
    try {
      const event = JSON.parse(String(data)) as ServerEvent;
      if (event.type === "error") {
        this.fail(`[${event.code}] ${event.message}`);
        return;
      }
      if (event.type !== "estimate") return;

      this.currentEstimate = this.toPositionEstimate(event.estimate);
      this.status = event.estimate.mode === "dead_reckoning"
        ? "GNSS_BLOCKED_SIMULATED"
        : "GNSS_AVAILABLE";
      this.notifyEstimate();
      this.notifyStatus();
    } catch {
      this.fail("IDR backend sent an invalid estimate message.");
    }
  }

  private toPositionEstimate(estimate: BackendEstimate): PositionEstimate {
    const sigma = Math.max(0.01, estimate.horizontalSigmaM);
    return {
      timestamp_ns: estimate.timestampNs,
      timestamp_ms: this.clock.toWallClockMs(estimate.timestampNs),
      latitude: estimate.latitudeDeg,
      longitude: estimate.longitudeDeg,
      altitude: estimate.altitudeM,
      speed: estimate.speedMps,
      heading: estimate.headingDeg,
      horizontal_accuracy: sigma,
      vertical_accuracy: Math.max(0.01, estimate.verticalSigmaM),
      position_source: estimate.isDeadReckoning ? "IDR" : "GNSS+INS",
      confidence: 1 / (1 + sigma / 10),
      valid: true,
      isDeadReckoning: estimate.isDeadReckoning,
    };
  }

  private emptyEstimate(): PositionEstimate {
    return {
      timestamp_ns: 0,
      timestamp_ms: 0,
      latitude: 0,
      longitude: 0,
      altitude: null,
      speed: null,
      heading: null,
      horizontal_accuracy: null,
      vertical_accuracy: null,
      position_source: "NONE",
      confidence: 0,
      valid: false,
      isDeadReckoning: false,
    };
  }

  private fail(message: string): void {
    if (this.disposed) return;
    console.warn(`[IDR backend] ${message}`);
    this.status = "NO_POSITION";
    this.notifyStatus();
  }

  private notifyEstimate(): void {
    this.estimateListeners.forEach((listener) => listener(this.currentEstimate));
  }

  private notifyStatus(): void {
    this.statusListeners.forEach((listener) => listener(this.status));
  }
}

class SessionClock {
  private originMs: number | null = null;

  public toSessionNs(timestampMs: number): number {
    if (!Number.isFinite(timestampMs)) {
      throw new Error("Phone callback timestamp must be finite.");
    }
    if (this.originMs === null) this.originMs = timestampMs;
    const relativeNs = Math.round((timestampMs - this.originMs) * 1_000_000);
    if (relativeNs < 0) {
      throw new Error("Phone callback timestamp regressed before session origin.");
    }
    return relativeNs;
  }

  public toWallClockMs(timestampNs: number): number {
    return (this.originMs ?? Date.now()) + timestampNs / 1_000_000;
  }

  public reset(): void {
    this.originMs = null;
  }
}

function toWebSocketBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
}

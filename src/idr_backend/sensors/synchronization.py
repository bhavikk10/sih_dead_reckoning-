""" accepts two already-normalized readings, so their units are guaranteed SI.
 confirms the samples truly belong together: correct sensor kinds, same device, same source, and same coordinate frame.
 rejects a pair that is too far apart in time. max_skew_ns stays explicit for now; later configuration will choose values per device.
 preserves both original timestamps for diagnostics.
 chooses the later timestamp as the combined sample's time. This is causal: in a real stream, we cannot use the pair until both readings exist."""


from .types import (
    NormalizedSensorSample, SensorKind, SynchronizedImuSample, CoordinateFrame, SensorSource
)

from collections import deque


def synchronize_pair( accelerometer: NormalizedSensorSample, gyroscope: NormalizedSensorSample, max_skew_ns: int) -> SynchronizedImuSample:
    """Build one IMU reading from a compatible accelero/gyro pair"""

    if max_skew_ns < 0:
        raise ValueError("max_skew_ns must be a whole number")

    if accelerometer.kind is not SensorKind.ACCELEROMETER:
        raise ValueError("The first sample must be an accelerometer reading.")

    if gyroscope.kind is not SensorKind.GYROSCOPE:
        raise ValueError("The second sample must be a gyroscope reading.")

    if accelerometer.source != gyroscope.source:
        raise ValueError("Cannot synchronize samples from different sources.")

    if accelerometer.source_id != gyroscope.source_id:
        raise ValueError("Cannot synchronize samples from different devices.")

    if accelerometer.frame != gyroscope.frame:
        raise ValueError("Cannot synchronize samples expressed in diff frames")

    skew_ns = abs(accelerometer.timestamp_ns - gyroscope.timestamp_ns)
    if skew_ns > max_skew_ns:
        raise ValueError(
            f"Accelerometer and gyroscope timestamps differ by {skew_ns} ns, "
            f"which exceeds the allowed skew of {max_skew_ns} ns."
        )

    return SynchronizedImuSample(
        #using the later timestamps since the combined reeaidng isnt really available until both physical measurements have arrived
        timestamp_ns = max(accelerometer.timestamp_ns, gyroscope.timestamp_ns),
        source = accelerometer.source,
        source_id = accelerometer.source_id,
        frame = accelerometer.frame,
        acceleration_mps2 = accelerometer.value,
        angular_velocity_radps = gyroscope.value,
        #preserve the originals so later diagnostics can expose the skew
        accelerometer_timestamp_ns = accelerometer.timestamp_ns,
        gyroscope_timestamp_ns = gyroscope.timestamp_ns,
    )


class ImuSynchronizer:
    """Holding the pending normalised readings from one physical IMU stream"""

    def __init__(self, max_skew_ns: int, max_pending_samples: int = 32) -> None:
        """Create bounded buffers for temporarily unmatched IMU readings."""

        if max_skew_ns < 0:
            raise ValueError("max_skew_ns must be zero or positive.")

        if max_pending_samples <= 0:
            raise ValueError("max_pending_samples must be positive.")

        self._max_skew_ns = max_skew_ns
        self._max_pending_samples = max_pending_samples                        # A bound prevents unlimited memory growth if one sensor stops reporting.
        self._pending_accelerometer: deque[NormalizedSensorSample] = deque()  # Acceleration and angular-velocity readings arrive independently.
        self._pending_gyroscope: deque[NormalizedSensorSample] = deque()

        self._source: SensorSource | None = None                               # One ImuSynchronizer instance must handle exactly one device and frame.
        self._source_id: str | None = None                                     # The first accepted sample establishes these values; push() will enforce them for every later sample
        self._frame: CoordinateFrame | None = None

        self._last_accelerometer_timestamp_ns: int | None = None
        self._last_gyroscope_timestamp_ns: int | None = None



    def push(self, sample: NormalizedSensorSample) -> tuple[SynchronizedImuSample, ...]:
        """Accept one normalized reading and return any newly matched IMU pairs."""

        if sample.kind not in (SensorKind.ACCELEROMETER, SensorKind.GYROSCOPE):
            raise ValueError("Immusynchronizer accepts only accelerometer or gyro readings")

        self._register_or_validate_stream(sample)    # Lock this synchronizer to one physical device and coordinate frame.
        self._append_pending_sample(sample)          # store the reading in its acceleration or gyro queue

        return self._drain_pairs()                   # match compatible readings and return the resulting imu samples


    def _register_or_validate_stream(self, sample: NormalizedSensorSample) -> None:
        """Bind this synchronizer to its first device, then enforce that identity."""

        if self._source is None:
            # The first accepted sample defines the one stream this instance owns.
            self._source = sample.source
            self._source_id = sample.source_id
            self._frame = sample.frame
            return

        if (sample.source != self._source or sample.source_id != self._source_id or sample.frame != self._frame):
            raise ValueError("Cannot mix multiple sensor devices or coordinate frames in one ImuSynchronizer.")    


    def _append_pending_sample(self, sample: NormalizedSensorSample) -> None:
        """Validate timestamp order and store a reading in its pending queue."""

        if sample.kind is SensorKind.ACCELEROMETER:
           pending_samples = self._pending_accelerometer
           previous_timestamp_ns = self._last_accelerometer_timestamp_ns
           sensor_name = "accelerometer"

        else:
            pending_samples = self._pending_gyroscope
            previous_timestamp_ns = self._last_gyroscope_timestamp_ns
            sensor_name = "gyroscope"        

        if previous_timestamp_ns is not None:
            if sample.timestamp_ns == previous_timestamp_ns:
                raise ValueError(f"Duplicate {sensor_name} timestamp: {sample.timestamp_ns} ns.")
            
            if sample.timestamp_ns < previous_timestamp_ns:
                raise ValueError(
                    f"Out-of-order {sensor_name} timestamp: "
                    f"{sample.timestamp_ns} ns arrived after "
                    f"{previous_timestamp_ns} ns.")

        if len(pending_samples) >= self._max_pending_samples:
            raise BufferError(
                f"Pending {sensor_name} buffer reached its limit of "
                f"{self._max_pending_samples} samples.")

        pending_samples.append(sample)

        if sample.kind is SensorKind.ACCELEROMETER:
            self._last_accelerometer_timestamp_ns = sample.timestamp_ns
        else:
            self._last_gyroscope_timestamp_ns = sample.timestamp_ns


    def _drain_pairs(self) -> tuple[SynchronizedImuSample, ...]:
        """Match queued readings in timestamp order and discard impossible matches."""

        synchronized_samples: list[SynchronizedImuSample] = []

        while self._pending_gyroscope and self._pending_accelerometer:
            accelerometer = self._pending_accelerometer[0]
            gyroscope = self._pending_gyroscope[0]

            timestamp_difference_ns = accelerometer.timestamp_ns - gyroscope.timestamp_ns

            if abs(timestamp_difference_ns) <= self._max_skew_ns:
                # The oldest readings are close enough in time, so they form one IMU sample and can be removed from their respective queues.    
                self._pending_gyroscope.popleft()
                self._pending_accelerometer.popleft()

                synchronized_samples.append(synchronize_pair(accelerometer= accelerometer, gyroscope=gyroscope, max_skew_ns=self._max_skew_ns))
                continue

            if timestamp_difference_ns < 0:
                # Accelerometer is older than gyroscope and already too far behind.
                # Since accelerometer timestamps must increase, no future gyroscope
                # reading can make this particular accelerometer reading match.
                self._pending_accelerometer.popleft()
            else:
                self._pending_gyroscope.popleft()

        return tuple(synchronized_samples)
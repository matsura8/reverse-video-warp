from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import BinaryIO

import cv2
import numpy as np
import torch

from .fal_adapter import FalModels
from .temporal import TemporalFieldSmoother
from .warp import inverse_warp_rgb


class OfflinePipelineError(RuntimeError):
    """Raised when decoding, CUDA processing, or encoding fails."""


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    frames_per_second: float
    duration_seconds: float | None
    has_audio: bool


@dataclass
class FaceTracker:
    detection_interval: int = 5
    scene_cut_threshold: float = 45.0
    _box: tuple[int, int, int, int] | None = None
    _previous_gray: np.ndarray | None = None
    _points: np.ndarray | None = None

    def __post_init__(self) -> None:
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self._detector = cv2.CascadeClassifier(str(cascade_path))
        if self._detector.empty():
            raise OfflinePipelineError("OpenCV frontal-face detector could not be loaded")

    def update(self, frame_rgb: np.ndarray, frame_index: int) -> tuple[int, int, int, int] | None:
        gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
        if self._previous_gray is not None:
            difference = float(cv2.absdiff(gray, self._previous_gray).mean())
            if difference >= self.scene_cut_threshold:
                self.reset()

        detect_now = self._box is None or frame_index % self.detection_interval == 0
        if detect_now:
            self._box = self._detect(gray)
            self._points = self._feature_points(gray, self._box)
        elif self._box is not None and self._previous_gray is not None:
            self._box = self._track(self._previous_gray, gray, self._box)
            if self._box is None:
                self._points = None

        self._previous_gray = gray
        return self._box

    def reset(self) -> None:
        self._box = None
        self._previous_gray = None
        self._points = None

    def _detect(self, gray: np.ndarray) -> tuple[int, int, int, int] | None:
        minimum = max(48, min(gray.shape) // 12)
        faces = self._detector.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=5,
            minSize=(minimum, minimum),
        )
        if len(faces) == 0:
            return None
        x, y, width, height = max(faces, key=lambda box: int(box[2]) * int(box[3]))
        return _padded_box((int(x), int(y), int(width), int(height)), gray.shape)

    def _feature_points(
        self, gray: np.ndarray, box: tuple[int, int, int, int] | None
    ) -> np.ndarray | None:
        if box is None:
            return None
        x, y, width, height = box
        mask = np.zeros_like(gray)
        mask[y : y + height, x : x + width] = 255
        return cv2.goodFeaturesToTrack(
            gray,
            maxCorners=80,
            qualityLevel=0.01,
            minDistance=5,
            mask=mask,
        )

    def _track(
        self,
        previous: np.ndarray,
        current: np.ndarray,
        box: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int] | None:
        if self._points is None or len(self._points) < 6:
            return None
        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            previous, current, self._points, None
        )
        if next_points is None or status is None:
            return None
        valid = status.reshape(-1).astype(bool)
        if int(valid.sum()) < 6:
            return None
        old = self._points.reshape(-1, 2)[valid]
        new = next_points.reshape(-1, 2)[valid]
        delta = np.median(new - old, axis=0)
        self._points = new.reshape(-1, 1, 2).astype(np.float32)
        x, y, width, height = box
        shifted = (int(round(x + delta[0])), int(round(y + delta[1])), width, height)
        return _clip_box(shifted, current.shape)


class Encoder:
    def __init__(
        self,
        destination: Path,
        *,
        source: Path,
        info: VideoInfo,
        encoder: str,
    ) -> None:
        self.destination = destination
        self.temporary = destination.with_name(f".{destination.stem}.partial{destination.suffix}")
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-video_size",
            f"{info.width}x{info.height}",
            "-framerate",
            f"{info.frames_per_second:.12g}",
            "-i",
            "pipe:0",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a?",
            "-c:v",
            encoder,
        ]
        if encoder == "h264_nvenc":
            command.extend(["-preset", "p4", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-b:v", "0"])
        else:
            command.extend(["-preset", "medium", "-crf", "18"])
        command.extend(
            ["-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", "-f", "mp4", str(self.temporary)]
        )
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE)
        if self.process.stdin is None:
            raise OfflinePipelineError("FFmpeg encoder did not expose standard input")
        self.stream: BinaryIO = self.process.stdin

    def write(self, frame_rgb: np.ndarray) -> None:
        self.stream.write(np.ascontiguousarray(frame_rgb, dtype=np.uint8).tobytes())

    def finish(self) -> None:
        self.stream.close()
        return_code = self.process.wait()
        if return_code != 0:
            raise OfflinePipelineError(
                f"FFmpeg encoder failed for {self.destination} with exit code {return_code}"
            )
        self.temporary.replace(self.destination)

    def abort(self) -> None:
        if not self.stream.closed:
            self.stream.close()
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        self.temporary.unlink(missing_ok=True)


def probe_video(source: Path) -> VideoInfo:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(source),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    video = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        None,
    )
    if video is None:
        raise OfflinePipelineError("input contains no video stream")
    width = int(video["width"])
    height = int(video["height"])
    numerator, denominator = video.get("avg_frame_rate", "0/1").split("/", 1)
    frames_per_second = float(numerator) / float(denominator)
    if width < 2 or height < 2 or frames_per_second <= 0:
        raise OfflinePipelineError("input video dimensions or frame rate are invalid")
    duration_value = video.get("duration") or payload.get("format", {}).get("duration")
    return VideoInfo(
        width=width,
        height=height,
        frames_per_second=frames_per_second,
        duration_seconds=float(duration_value) if duration_value else None,
        has_audio=any(
            stream.get("codec_type") == "audio" for stream in payload.get("streams", [])
        ),
    )


def process_video(
    source: Path,
    output: Path,
    *,
    diagnostic: Path | None,
    comparison: Path | None,
    fal_root: Path,
    device: str,
    threshold: float,
    detection_interval: int,
    encoder: str,
) -> dict[str, int | float | bool]:
    if not 0.0 <= threshold <= 1.0:
        raise OfflinePipelineError("threshold must be between 0 and 1")
    if detection_interval < 1:
        raise OfflinePipelineError("detection interval must be positive")

    info = probe_video(source)
    models = FalModels(fal_root, device=device)
    tracker = FaceTracker(detection_interval=detection_interval)
    smoother = TemporalFieldSmoother()
    destinations = [output, diagnostic, comparison]
    encoders = [
        Encoder(path, source=source, info=info, encoder=encoder)
        for path in destinations
        if path is not None
    ]
    decoder = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
    )
    if decoder.stdout is None:
        raise OfflinePipelineError("FFmpeg decoder did not expose standard output")

    frame_bytes = info.width * info.height * 3
    frame_index = 0
    detected_frames = 0
    corrected_frames = 0
    lost_frames = 0
    last_probability = 0.0
    cached_field: torch.Tensor | None = None
    cached_box: tuple[int, int, int, int] | None = None
    try:
        while True:
            raw = decoder.stdout.read(frame_bytes)
            if not raw:
                break
            if len(raw) != frame_bytes:
                raise OfflinePipelineError("decoder returned a truncated frame")
            original = np.frombuffer(raw, dtype=np.uint8).reshape(
                info.height, info.width, 3
            ).copy()
            corrected = original.copy()
            box = tracker.update(original, frame_index)
            heatmap = np.zeros_like(original)
            if box is None:
                lost_frames += 1
                smoother.reset()
                cached_field = None
                cached_box = None
            else:
                detected_frames += 1
                x, y, width, height = box
                crop = original[y : y + height, x : x + width]
                infer_now = cached_field is None or cached_box != box or frame_index % detection_interval == 0
                if infer_now:
                    result = models.infer(torch.from_numpy(crop.copy()))
                    last_probability = result.manipulation_probability
                    cached_field = _resize_field(result.displacement, width, height)
                    cached_box = box
                if cached_field is not None and last_probability >= threshold:
                    # Reaching this branch means the caller accepted the model score.
                    # Keep the smoother stable at very low forced-test thresholds while
                    # preserving the actual confidence weighting above its safety floor.
                    smoothing_confidence = max(
                        last_probability, smoother.confidence_floor
                    )
                    smoothed = smoother.update(
                        cached_field, confidence=smoothing_confidence
                    )
                    if smoothed is not None:
                        warped = inverse_warp_rgb(
                            torch.from_numpy(crop.copy()), smoothed, device=device
                        ).cpu().numpy()
                        corrected[y : y + height, x : x + width] = _feather_composite(
                            crop, warped
                        )
                        heatmap[y : y + height, x : x + width] = _flow_heatmap(smoothed)
                        corrected_frames += 1

            frames = [corrected]
            if diagnostic is not None:
                frames.append(heatmap)
            if comparison is not None:
                split = corrected.copy()
                split[:, : info.width // 2] = original[:, : info.width // 2]
                frames.append(split)
            for writer, frame in zip(encoders, frames, strict=True):
                writer.write(frame)
            frame_index += 1

        decoder.stdout.close()
        if decoder.wait() != 0:
            raise OfflinePipelineError("FFmpeg decoder failed")
        if frame_index == 0:
            raise OfflinePipelineError("input produced no decoded frames")
        for writer in encoders:
            writer.finish()
    except BaseException:
        if decoder.poll() is None:
            decoder.kill()
        decoder.wait()
        for writer in encoders:
            writer.abort()
        raise

    return {
        "frames": frame_index,
        "detectedFrames": detected_frames,
        "correctedFrames": corrected_frames,
        "bypassFrames": frame_index - corrected_frames,
        "trackingLostFrames": lost_frames,
        "lastManipulationProbability": last_probability,
        "audioPreserved": info.has_audio,
    }


def _padded_box(
    box: tuple[int, int, int, int], shape: tuple[int, ...]
) -> tuple[int, int, int, int]:
    x, y, width, height = box
    padding_x = int(width * 0.35)
    padding_top = int(height * 0.55)
    padding_bottom = int(height * 0.25)
    return _clip_box(
        (
            x - padding_x,
            y - padding_top,
            width + (2 * padding_x),
            height + padding_top + padding_bottom,
        ),
        shape,
    )


def _clip_box(
    box: tuple[int, int, int, int], shape: tuple[int, ...]
) -> tuple[int, int, int, int]:
    x, y, width, height = box
    frame_height, frame_width = shape[:2]
    left = max(0, min(frame_width - 2, x))
    top = max(0, min(frame_height - 2, y))
    right = max(left + 2, min(frame_width, x + width))
    bottom = max(top + 2, min(frame_height, y + height))
    return left, top, right - left, bottom - top


def _resize_field(field: torch.Tensor, width: int, height: int) -> torch.Tensor:
    source_height, source_width, _ = field.shape
    channels = field.permute(2, 0, 1).unsqueeze(0)
    resized = torch.nn.functional.interpolate(
        channels,
        size=(height, width),
        mode="bilinear",
        align_corners=True,
    )[0].permute(1, 2, 0).contiguous()
    resized[..., 0].mul_(width / source_width)
    resized[..., 1].mul_(height / source_height)
    return resized


def _feather_composite(original: np.ndarray, warped: np.ndarray) -> np.ndarray:
    height, width = original.shape[:2]
    mask = np.zeros((height, width), dtype=np.float32)
    cv2.ellipse(
        mask,
        (width // 2, height // 2),
        (max(1, int(width * 0.42)), max(1, int(height * 0.45))),
        0,
        0,
        360,
        1.0,
        -1,
    )
    sigma = max(1.0, min(width, height) * 0.04)
    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma, sigmaY=sigma)[..., None]
    return np.clip((warped * mask) + (original * (1.0 - mask)), 0, 255).astype(np.uint8)


def _flow_heatmap(field: torch.Tensor) -> np.ndarray:
    magnitude = torch.linalg.vector_norm(field, dim=-1).detach().cpu().numpy()
    maximum = float(np.percentile(magnitude, 99.0))
    if maximum <= 0:
        return np.zeros((*magnitude.shape, 3), dtype=np.uint8)
    scaled = np.clip(magnitude * (255.0 / maximum), 0, 255).astype(np.uint8)
    colored = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
    return cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)


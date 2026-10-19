from __future__ import annotations

import base64
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import torch

from .fal_adapter import FalModels
from .offline import FaceTracker, _feather_composite, _resize_field
from .temporal import TemporalFieldSmoother
from .warp import inverse_warp_rgb


class LiveWorkerError(ValueError):
    """Raised when a live-frame request is malformed."""


class LiveProcessor:
    def __init__(self, fal_root: Path, *, device: str, threshold: float) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise LiveWorkerError("threshold must be between 0 and 1")
        self.models = FalModels(fal_root, device=device)
        self.device = device
        self.threshold = threshold
        self.tracker = FaceTracker(detection_interval=5)
        self.smoother = TemporalFieldSmoother()
        self.frame_index = 0
        self.cached_field: torch.Tensor | None = None
        self.cached_box: tuple[int, int, int, int] | None = None
        self.probability = 0.0

    def process_jpeg(self, payload: bytes) -> tuple[bytes, dict[str, float | bool]]:
        encoded = np.frombuffer(payload, dtype=np.uint8)
        frame_bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame_bgr is None:
            raise LiveWorkerError("frame is not a valid JPEG image")
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        corrected = frame_rgb.copy()
        box = self.tracker.update(frame_rgb, self.frame_index)
        applied = False
        if box is None:
            self.smoother.reset()
            self.cached_field = None
            self.cached_box = None
        else:
            x, y, width, height = box
            crop = frame_rgb[y : y + height, x : x + width]
            infer_now = (
                self.cached_field is None
                or self.cached_box != box
                or self.frame_index % self.tracker.detection_interval == 0
            )
            if infer_now:
                result = self.models.infer(torch.from_numpy(crop.copy()))
                self.probability = result.manipulation_probability
                self.cached_field = _resize_field(result.displacement, width, height)
                self.cached_box = box
            if self.cached_field is not None and self.probability >= self.threshold:
                confidence = max(self.probability, self.smoother.confidence_floor)
                field = self.smoother.update(self.cached_field, confidence=confidence)
                if field is not None:
                    warped = inverse_warp_rgb(
                        torch.from_numpy(crop.copy()), field, device=self.device
                    ).cpu().numpy()
                    corrected[y : y + height, x : x + width] = _feather_composite(
                        crop, warped
                    )
                    applied = True
        self.frame_index += 1
        output_bgr = cv2.cvtColor(corrected, cv2.COLOR_RGB2BGR)
        success, output = cv2.imencode(
            ".jpg", output_bgr, [cv2.IMWRITE_JPEG_QUALITY, 88]
        )
        if not success:
            raise LiveWorkerError("JPEG encoding failed")
        return output.tobytes(), {
            "applied": applied,
            "faceDetected": box is not None,
            "manipulationProbability": self.probability,
        }


def parse_frame_request(line: str) -> bytes:
    request = json.loads(line)
    if not isinstance(request, dict) or set(request) != {"frame"}:
        raise LiveWorkerError("request must contain only frame")
    value = request["frame"]
    if not isinstance(value, str) or len(value) > 16_000_000:
        raise LiveWorkerError("frame must be bounded base64 text")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise LiveWorkerError("frame is not valid base64") from error


def serve(fal_root: Path, *, device: str, threshold: float) -> int:
    processor = LiveProcessor(fal_root, device=device, threshold=threshold)
    print(json.dumps({"ready": True, "device": device}), flush=True)
    for line in sys.stdin:
        try:
            payload = parse_frame_request(line)
            output, metrics = processor.process_jpeg(payload)
            response = {
                "ok": True,
                "frame": base64.b64encode(output).decode("ascii"),
                **metrics,
            }
        except (LiveWorkerError, json.JSONDecodeError, ValueError) as error:
            response = {"ok": False, "error": str(error)}
        print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0

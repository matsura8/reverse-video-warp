from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from reversewarp_worker.offline import OfflinePipelineError, process_video


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ReverseWarp offline CUDA processor")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--fal-root", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--detection-interval", type=int, default=5)
    parser.add_argument("--encoder", choices=("h264_nvenc", "libx264"), default="h264_nvenc")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = process_video(
            args.input,
            args.output,
            diagnostic=args.diagnostic,
            comparison=args.comparison,
            fal_root=args.fal_root,
            device=args.device,
            threshold=args.threshold,
            detection_interval=args.detection_interval,
            encoder=args.encoder,
        )
    except (OfflinePipelineError, OSError, ValueError) as error:
        print(f"offline processing failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


from __future__ import annotations

import argparse
from pathlib import Path

from reversewarp_worker.live import serve


def main() -> int:
    parser = argparse.ArgumentParser(description="ReverseWarp persistent live CUDA worker")
    parser.add_argument("--fal-root", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    return serve(args.fal_root, device=args.device, threshold=args.threshold)


if __name__ == "__main__":
    raise SystemExit(main())

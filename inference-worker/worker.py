from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from reversewarp_worker.cuda_runtime import DeviceError, inspect_device
from reversewarp_worker.fal_adapter import FalAdapterError, FalModels
from reversewarp_worker.protocol import serve
from reversewarp_worker.warp import run_cuda_self_test


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ReverseWarp CUDA inference worker")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="allow the CPU debug fallback; never enabled by the production launcher",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="print device information as JSON and exit",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run a deterministic inverse-warp kernel test and exit",
    )
    parser.add_argument(
        "--fal-root",
        type=Path,
        help="trusted pinned FALdetector checkout used only during worker startup",
    )
    parser.add_argument(
        "--fal-self-test",
        action="store_true",
        help="load both pinned FAL models and run a synthetic CUDA inference",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        device = inspect_device(args.device, allow_cpu=args.allow_cpu)
    except DeviceError as error:
        print(f"ReverseWarp worker startup failed: {error}", file=sys.stderr)
        return 2

    if args.probe:
        print(json.dumps(device.to_dict(), indent=2, sort_keys=True))
        return 0

    if args.self_test:
        if device.kind != "cuda":
            print("CUDA self-test requires a cuda:N device", file=sys.stderr)
            return 2
        result = run_cuda_self_test(device.resolved)
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0 if result.identity_max_error == 0 and result.deterministic else 3

    if args.fal_self_test:
        if device.kind != "cuda" or args.fal_root is None:
            print("FAL self-test requires cuda:N and --fal-root", file=sys.stderr)
            return 2
        try:
            result = FalModels(args.fal_root, device=device.resolved).self_test()
        except FalAdapterError as error:
            print(f"FAL self-test failed: {error}", file=sys.stderr)
            return 3
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0 if result.displacement_finite else 3

    print(
        f"ReverseWarp worker ready on {device.resolved} ({device.name})",
        file=sys.stderr,
    )
    serve(sys.stdin, sys.stdout, device_info=device.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


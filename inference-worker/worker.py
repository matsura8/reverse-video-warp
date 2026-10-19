from __future__ import annotations

import argparse
import json
import sys

from reversewarp_worker.cuda_runtime import DeviceError, inspect_device
from reversewarp_worker.protocol import serve


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

    print(
        f"ReverseWarp worker ready on {device.resolved} ({device.name})",
        file=sys.stderr,
    )
    serve(sys.stdin, sys.stdout, device_info=device.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


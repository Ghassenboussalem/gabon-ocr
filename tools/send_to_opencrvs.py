#!/usr/bin/env python3
"""Send a processed document to OpenCRVS as a prefilled birth notification.

    # inspect the payload without sending anything:
    python tools/send_to_opencrvs.py runs/test_coteivoire --dry-run

    # actually notify (needs OPENCRVS_* config in .env):
    python tools/send_to_opencrvs.py runs/test_coteivoire
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.env import load_dotenv

load_dotenv()

from pipeline.opencrvs_export import DEFAULT_THRESHOLD, send_report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", help="runs/<doc> directory (must contain report.json)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="minimum field score to prefill (default %(default)s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the declaration payload without calling OpenCRVS")
    args = ap.parse_args()

    report = Path(args.run_dir) / "report.json"
    if not report.exists():
        sys.exit(f"no report.json in {args.run_dir} — run the pipeline first")

    result = send_report(report, threshold=args.threshold, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.dry_run:
        print("\n(dry run — nothing sent)")
    else:
        print(f"\nnotified OpenCRVS: event {result['event_id']}")


if __name__ == "__main__":
    main()

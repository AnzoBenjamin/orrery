#!/usr/bin/env python3
"""Regenerate the committed synthetic end-to-end fixture suite."""

from __future__ import annotations

import argparse
from pathlib import Path

from orrery_lab.suite.fixtures import materialize_fixture_suite

REPOSITORY = Path(__file__).resolve().parents[3]
MANIFEST = REPOSITORY / "tools/lab/fixtures/e2e.toml"
DESTINATION = REPOSITORY / "e2e/fixtures/synthetic-lab"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate in a temporary directory and fail if committed bytes differ",
    )
    args = parser.parse_args()
    result = materialize_fixture_suite(MANIFEST, DESTINATION, check=args.check)
    action = "verified" if args.check else "generated"
    print(f"{action} {len(result.suite.clips)} clips at {result.directory}")


if __name__ == "__main__":
    main()

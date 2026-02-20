#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "Running pylogrouter mock stream (interval: 3s). Press Ctrl+C to stop."
PYTHONPATH="$ROOT_DIR/src" python3 example.py --mock-stream --interval 3

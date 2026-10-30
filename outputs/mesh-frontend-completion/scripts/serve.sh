#!/bin/sh
cd "$(dirname "$0")/.." && exec npx next start -p "${1:-3100}"

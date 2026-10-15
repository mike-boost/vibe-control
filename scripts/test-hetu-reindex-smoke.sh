#!/usr/bin/env bash
# Optional real Hetu reindex smoke. REQUIRES explicit owner approval.
# Markers conceptually: real_hetu + mutation. NOT part of any default gate.
# Prefer fake/unit reindex coverage (tests/test_hetu_reindex.py). This script
# only documents the isolated apply path — do not run casually.
set -euo pipefail
echo "Refuse: real Hetu reindex smoke is owner-gated and not part of default land."
echo "Use fake/unit tests for TDD confidence. If you must run real reindex:"
echo "  1) isolated temp repo + temp state + temp CBM_CACHE_DIR"
echo "  2) external config with components.hetu.enabled=true"
echo "  3) vibe hetu reindex --dry-run --json  # capture plan_binding"
echo "  4) vibe hetu reindex --apply --expect-plan-binding <hash> --confirm-hetu-reindex-apply --json"
exit 2

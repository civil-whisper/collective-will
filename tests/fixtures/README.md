# Fixtures Notes

CI uses `pipeline_replay_fixture.json` for a no-network pipeline replay test.
It must stay deterministic and provider-free.

## Refresh replay fixture

1. (Optional baseline) regenerate comprehensive cache locally:
   - `GENERATE_PIPELINE_CACHE=1 uv run pytest tests/test_pipeline/test_pipeline_comprehensive.py -s`
2. Curate/update `pipeline_replay_fixture.json` with representative inputs and canonical outputs.
3. Verify replay path:
   - `uv run pytest tests/test_pipeline/test_pipeline_cached_replay.py -q`

Do not require paid LLM calls in CI.

To run the same backend checks as GitHub CI locally:
- `bash scripts/ci-backend.sh`

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.config import get_settings
from src.pipeline.replay import (
    ReplayCachingLLMRouter,
    load_submissions_from_db,
    load_submissions_from_json,
    replay_metadata,
    replay_submissions,
    write_submission_snapshot,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay stored submissions through the current pipeline logic without mutating live state."
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        help="Load submissions from a JSON snapshot instead of a source database.",
    )
    parser.add_argument(
        "--source-db-url",
        help="Database URL to export submissions from. Defaults to configured DATABASE_URL.",
    )
    parser.add_argument(
        "--export-json",
        type=Path,
        help="Optional path to write the loaded submission snapshot before replay.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("data/replay/submission-replay-report.json"),
        help="Path to write the replay report JSON.",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=Path("data/replay/submission-replay-cache.json.gz"),
        help="Incremental cache file for LLM completions and embeddings.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of submissions to load.",
    )
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    settings = get_settings()

    try:
        if args.input_json:
            submissions = load_submissions_from_json(args.input_json, limit=args.limit)
            source = f"json:{args.input_json}"
        else:
            submissions = await load_submissions_from_db(database_url=args.source_db_url, limit=args.limit)
            source = "database:configured" if not args.source_db_url else "database:explicit"
    except Exception as exc:
        if args.input_json:
            raise SystemExit(f"Failed to load submission snapshot from {args.input_json}: {exc}") from exc
        configured = args.source_db_url or settings.database_url
        raise SystemExit(
            "Failed to load submissions from the source database. "
            f"Tried: {configured}. "
            "Either provide `--input-json path/to/submissions.json` or point `--source-db-url` at a reachable database."
        ) from exc

    if not submissions:
        raise SystemExit("No submissions loaded for replay.")

    if args.export_json:
        write_submission_snapshot(args.export_json, submissions)

    router = ReplayCachingLLMRouter(cache_path=args.cache_path, settings=settings)
    fingerprint = replay_metadata(source=source, submissions=submissions)["dataset_fingerprint"]
    router.save(fingerprint=fingerprint)

    report = await replay_submissions(submissions=submissions, llm_router=router)
    full_report = {
        "metadata": replay_metadata(source=source, submissions=submissions, router=router),
        "report": report,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(full_report, ensure_ascii=False, indent=2), encoding="utf-8")
    router.save(fingerprint=fingerprint)

    print(
        json.dumps(
            {
                "output_json": str(args.output_json),
                "cache_path": str(args.cache_path),
                "submission_count": report["submission_count"],
                "candidate_count": report["candidate_count"],
                "cluster_count": report["cluster_count"],
                "rejected_count": report["rejected_count"],
                "degradation_count": report.get("degradation_count", 0),
                "degradation_summary": report.get("degradation_summary", {}),
                "total_cost_usd": full_report["metadata"].get("router", {}).get("total_cost_usd"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))

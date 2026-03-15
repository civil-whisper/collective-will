from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import date

from anyio import Path as AsyncPath


@dataclass(frozen=True, slots=True)
class AuditArtifactPaths:
    day_iso: str
    day_dir: AsyncPath
    bundle: AsyncPath
    manifest: AsyncPath
    ots_proof: AsyncPath


def parse_day(day: str) -> str:
    parsed = date.fromisoformat(day)
    return parsed.isoformat()


def day_artifact_paths(*, base_dir: str, day_iso: str) -> AuditArtifactPaths:
    normalized_day = parse_day(day_iso)
    day_dir = AsyncPath(base_dir) / normalized_day
    return AuditArtifactPaths(
        day_iso=normalized_day,
        day_dir=day_dir,
        bundle=day_dir / f"audit-{normalized_day}.jsonl.gz",
        manifest=day_dir / f"manifest-{normalized_day}.json",
        ots_proof=day_dir / f"audit-{normalized_day}.ots",
    )


def sha256_file_sync(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def bundle_contains_hash_sync(path: str, entry_hash: str) -> bool:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("hash") == entry_hash:
                return True
    return False


async def read_json_file(path: AsyncPath) -> dict[str, object] | None:
    if not await path.exists():
        return None
    parsed = json.loads(await path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else None


def audit_download_urls(day_iso: str) -> dict[str, str]:
    return {
        "bundle": f"/analytics/audit-bundles/{day_iso}/bundle",
        "manifest": f"/analytics/audit-bundles/{day_iso}/manifest",
        "ots_proof": f"/analytics/audit-bundles/{day_iso}/ots",
    }

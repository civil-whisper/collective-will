from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from bitcoin.rpc import Proxy
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
from opentimestamps.core.op import OpAppend, OpSHA256
from opentimestamps.core.serialize import StreamDeserializationContext, StreamSerializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp
from otsclient.cache import TimestampCache
from otsclient.cmds import create_timestamp, upgrade_timestamp, verify_timestamp
from sqlalchemy import Date, DateTime, String, and_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.config import Settings
from src.db.connection import Base
from src.db.evidence import EvidenceLogEntry, append_evidence, apply_visibility_tier, isoformat_z


@dataclass(frozen=True, slots=True)
class AuditBundleResult:
    day: date
    entry_count: int
    bundle_sha256: str
    storage_path: str
    first_entry_id: int
    last_entry_id: int
    first_hash: str
    last_hash: str


@dataclass(frozen=True, slots=True)
class TimestampingResult:
    provider: str
    status: str
    ots_proof_path: str | None
    verified_before: str | None
    bitcoin_block_height: int | None
    error_type: str | None = None


class DailyAnchor(Base):
    __tablename__ = "daily_anchors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    published_receipt: Mapped[str | None] = mapped_column(String, nullable=True)
    anchor_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


def _pair_hash(left: str, right: str) -> str:
    payload = f"{left}{right}".encode()
    return hashlib.sha256(payload).hexdigest()


def compute_merkle_root(leaves: list[str]) -> str:
    if not leaves:
        raise ValueError("Cannot compute Merkle root for empty leaves")
    level = leaves[:]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level: list[str] = []
        for idx in range(0, len(level), 2):
            next_level.append(_pair_hash(level[idx], level[idx + 1]))
        level = next_level
    return level[0]


async def compute_daily_merkle_root(session: AsyncSession, day: date) -> str | None:
    start = datetime.combine(day, time.min).replace(tzinfo=UTC)
    end = start + timedelta(days=1)
    result = await session.execute(
        select(EvidenceLogEntry)
        .where(and_(EvidenceLogEntry.timestamp >= start, EvidenceLogEntry.timestamp < end))
        .order_by(EvidenceLogEntry.id.asc())
    )
    entries = list(result.scalars().all())
    if not entries:
        return None

    root = compute_merkle_root([entry.hash for entry in entries])
    existing = await session.execute(select(DailyAnchor).where(DailyAnchor.day == day))
    anchor = existing.scalar_one_or_none()
    if anchor is None:
        anchor = DailyAnchor(day=day, merkle_root=root, anchor_metadata={"entry_count": len(entries)})
        session.add(anchor)
        await session.flush()
        await append_evidence(
            session=session,
            event_type="anchor_computed",
            entity_type="daily_anchor",
            entity_id=entries[-1].entity_id,
            payload={"day": day.isoformat(), "merkle_root": root, "entry_count": len(entries)},
        )
    return root


class _HashingWriter:
    """Write-through wrapper that tracks SHA-256 of emitted bytes."""

    def __init__(self, path: Path) -> None:
        self._file = path.open("wb")
        self._hasher = hashlib.sha256()

    def write(self, data: bytes) -> int:
        self._hasher.update(data)
        return self._file.write(data)

    def close(self) -> None:
        self._file.close()

    def flush(self) -> None:
        self._file.flush()

    def hexdigest(self) -> str:
        return self._hasher.hexdigest()


DEFAULT_OPENTIMESTAMPS_CALENDARS = (
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://a.pool.eternitywall.com",
    "https://ots.btc.catallaxy.com",
)


def _timestamping_placeholder(provider: str) -> TimestampingResult:
    if provider == "none":
        return TimestampingResult(
            provider="none",
            status="disabled",
            ots_proof_path=None,
            verified_before=None,
            bitcoin_block_height=None,
        )
    return TimestampingResult(
        provider=provider,
        status="pending",
        ots_proof_path=None,
        verified_before=None,
        bitcoin_block_height=None,
    )


def _opentimestamps_cache_dir(output_dir: str | Path) -> Path:
    cache_dir = Path(output_dir) / ".ots-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _ots_args(
    settings: Settings,
    *,
    cache_dir: Path,
    use_bitcoin: bool,
) -> SimpleNamespace:
    calendar_urls = settings.opentimestamps_calendar_url_list() or list(DEFAULT_OPENTIMESTAMPS_CALENDARS)
    required_calendar_count = settings.opentimestamps_required_calendar_count
    if required_calendar_count <= 0 or required_calendar_count > len(calendar_urls):
        raise ValueError("OpenTimestamps required calendar count must be between 1 and the calendar URL count")
    return SimpleNamespace(
        setup_bitcoin=(
            (lambda: Proxy(service_url=settings.opentimestamps_bitcoin_node_url))
            if use_bitcoin and settings.opentimestamps_bitcoin_node_url
            else None
        ),
        use_btc_wallet=False,
        m=required_calendar_count,
        timeout=settings.opentimestamps_timeout_seconds,
        cache=TimestampCache(str(cache_dir)),
        calendar_urls=calendar_urls,
        whitelist=set(calendar_urls),
        use_bitcoin=use_bitcoin,
        wait=False,
    )


def _root_digest(root: str) -> bytes:
    return hashlib.sha256(root.encode("utf-8")).digest()


def _new_detached_timestamp(root: str) -> tuple[DetachedTimestampFile, Timestamp]:
    detached = DetachedTimestampFile(OpSHA256(), Timestamp(_root_digest(root)))
    merkle_tip = detached.timestamp.ops.add(OpAppend(os.urandom(16))).ops.add(OpSHA256())
    return detached, merkle_tip


def _load_detached_timestamp(path: Path) -> DetachedTimestampFile:
    with path.open("rb") as handle:
        return DetachedTimestampFile.deserialize(StreamDeserializationContext(handle))


def _store_detached_timestamp(path: Path, detached: DetachedTimestampFile) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("wb") as handle:
        detached.serialize(StreamSerializationContext(handle))
    temp_path.replace(path)


def _bitcoin_block_height(detached: DetachedTimestampFile) -> int | None:
    heights = [
        attestation.height
        for _, attestation in detached.timestamp.all_attestations()
        if isinstance(attestation, BitcoinBlockHeaderAttestation)
    ]
    return min(heights) if heights else None


def _has_any_attestation(detached: DetachedTimestampFile) -> bool:
    return any(True for _ in detached.timestamp.all_attestations())


def _timestamping_result_from_detached(
    *,
    detached: DetachedTimestampFile,
    ots_path: Path,
    previous_status: str | None,
    previous_verified_before: str | None,
    settings: Settings,
    cache_dir: Path,
) -> TimestampingResult | None:
    if not _has_any_attestation(detached):
        return None

    bitcoin_block_height = _bitcoin_block_height(detached)
    status = "stamped"
    verified_before = None
    if previous_status == "verified" and previous_verified_before and bitcoin_block_height is not None:
        status = "verified"
        verified_before = previous_verified_before
    elif bitcoin_block_height is not None and settings.opentimestamps_bitcoin_node_url:
        verify_args = _ots_args(settings, cache_dir=cache_dir, use_bitcoin=True)
        if verify_timestamp(detached.timestamp, verify_args):
            status = "verified"
            verified_before = isoformat_z(datetime.now(UTC))

    return TimestampingResult(
        provider="opentimestamps",
        status=status,
        ots_proof_path=str(ots_path),
        verified_before=verified_before,
        bitcoin_block_height=bitcoin_block_height,
    )


async def export_daily_audit_bundle(
    session: AsyncSession,
    day: date,
    *,
    output_dir: str | Path,
    emit_evidence: bool = True,
) -> AuditBundleResult | None:
    start = datetime.combine(day, time.min).replace(tzinfo=UTC)
    end = start + timedelta(days=1)
    result = await session.execute(
        select(EvidenceLogEntry)
        .where(and_(EvidenceLogEntry.timestamp >= start, EvidenceLogEntry.timestamp < end))
        .order_by(EvidenceLogEntry.id.asc())
    )
    entries = list(result.scalars().all())
    if not entries:
        return None

    # Delayed fields must remain hidden while a cycle is active, consistent with /analytics/evidence.
    active_cycle_ids: set[UUID] = set()
    from src.models.vote import VotingCycle

    active_result = await session.execute(select(VotingCycle.id).where(VotingCycle.status == "active"))
    for row in active_result.all():
        active_cycle_ids.add(row[0])

    day_dir = Path(output_dir) / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = day_dir / f"audit-{day.isoformat()}.jsonl.gz"

    writer = _HashingWriter(bundle_path)
    try:
        with gzip.GzipFile(filename="", mode="wb", fileobj=writer, mtime=0) as gz:
            for entry in entries:
                cycle_id_raw = entry.payload.get("cycle_id") if isinstance(entry.payload, dict) else None
                cycle_closed = True
                if cycle_id_raw:
                    try:
                        cycle_closed = UUID(str(cycle_id_raw)) not in active_cycle_ids
                    except (ValueError, AttributeError):
                        cycle_closed = True
                public_entry = {
                    "id": entry.id,
                    "timestamp": isoformat_z(entry.timestamp),
                    "event_type": entry.event_type,
                    "entity_type": entry.entity_type,
                    "entity_id": str(entry.entity_id),
                    "payload": apply_visibility_tier(entry.event_type, entry.payload, cycle_closed=cycle_closed),
                    "hash": entry.hash,
                    "prev_hash": entry.prev_hash,
                }
                line = json.dumps(
                    public_entry,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                gz.write(line)
                gz.write(b"\n")
    finally:
        writer.close()

    bundle_sha256 = writer.hexdigest()
    if emit_evidence:
        entity_id = await _anchor_entity_id(session, day)
        await append_evidence(
            session=session,
            event_type="audit_bundle_generated",
            entity_type="daily_anchor",
            entity_id=entity_id,
            payload={
                "day": day.isoformat(),
                "entry_count": len(entries),
                "bundle_sha256": bundle_sha256,
                "storage_path": str(bundle_path),
            },
        )
    return AuditBundleResult(
        day=day,
        entry_count=len(entries),
        bundle_sha256=bundle_sha256,
        storage_path=str(bundle_path),
        first_entry_id=entries[0].id,
        last_entry_id=entries[-1].id,
        first_hash=entries[0].hash,
        last_hash=entries[-1].hash,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def publish_daily_audit_bundle_metadata(
    session: AsyncSession,
    *,
    day: date,
    merkle_root: str,
    bundle: AuditBundleResult,
    output_dir: str | Path,
    timestamping: TimestampingResult | None = None,
    emit_evidence: bool = True,
) -> tuple[str, str]:
    root_dir = Path(output_dir)
    day_dir = root_dir / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = day_dir / f"manifest-{day.isoformat()}.json"
    index_path = root_dir / "index.json"
    generated_at = isoformat_z(datetime.now(UTC))
    entity_id = await _anchor_entity_id(session, day)
    timestamping_result = timestamping or _timestamping_placeholder("opentimestamps")

    try:
        manifest = {
            "schema_version": 1,
            "day_utc": day.isoformat(),
            "entry_count": bundle.entry_count,
            "first_entry_id": bundle.first_entry_id,
            "last_entry_id": bundle.last_entry_id,
            "first_hash": bundle.first_hash,
            "last_hash": bundle.last_hash,
            "daily_merkle_root": merkle_root,
            "bundle_sha256": bundle.bundle_sha256,
            "generated_at": generated_at,
            "visibility_policy_version": 1,
            "event_catalog_version": "v1",
            "timestamping": {
                "provider": timestamping_result.provider,
                "status": timestamping_result.status,
                "ots_proof_path": timestamping_result.ots_proof_path,
                "verified_before": timestamping_result.verified_before,
                "bitcoin_block_height": timestamping_result.bitcoin_block_height,
            },
        }
        _write_json(manifest_path, manifest)

        index: dict[str, Any]
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
        else:
            index = {"schema_version": 1, "updated_at": generated_at, "days": []}

        days: list[dict[str, Any]] = []
        existing_days = index.get("days")
        if isinstance(existing_days, list):
            for row in existing_days:
                if isinstance(row, dict) and row.get("day_utc") != day.isoformat():
                    days.append(row)

        days.append(
            {
                "day_utc": day.isoformat(),
                "entry_count": bundle.entry_count,
                "daily_merkle_root": merkle_root,
                "bundle_path": bundle.storage_path,
                "manifest_path": str(manifest_path),
                "ots_proof_path": timestamping_result.ots_proof_path,
                "timestamping_status": timestamping_result.status,
            }
        )
        days.sort(key=lambda item: str(item.get("day_utc", "")), reverse=True)
        index["schema_version"] = 1
        index["updated_at"] = generated_at
        index["days"] = days
        _write_json(index_path, index)

        if emit_evidence:
            await append_evidence(
                session=session,
                event_type="audit_bundle_publish_succeeded",
                entity_type="daily_anchor",
                entity_id=entity_id,
                payload={
                    "day": day.isoformat(),
                    "bundle_sha256": bundle.bundle_sha256,
                    "manifest_path": str(manifest_path),
                    "index_path": str(index_path),
                },
            )
    except Exception as exc:
        if emit_evidence:
            await append_evidence(
                session=session,
                event_type="audit_bundle_publish_failed",
                entity_type="daily_anchor",
                entity_id=entity_id,
                payload={
                    "day": day.isoformat(),
                    "bundle_sha256": bundle.bundle_sha256,
                    "error_type": type(exc).__name__,
                },
            )
        raise

    return str(manifest_path), str(index_path)


async def publish_daily_merkle_root(
    root: str,
    day: date,
    settings: Settings,
    session: AsyncSession | None = None,
) -> TimestampingResult | None:
    day_dir = Path(settings.audit_bundle_output_dir) / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = day_dir / f"manifest-{day.isoformat()}.json"
    ots_path = day_dir / f"audit-{day.isoformat()}.ots"
    cache_dir = _opentimestamps_cache_dir(settings.audit_bundle_output_dir)

    previous_status: str | None = None
    previous_verified_before: str | None = None
    if manifest_path.exists():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        timestamping = existing_manifest.get("timestamping")
        if isinstance(timestamping, dict):
            status_value = timestamping.get("status")
            if isinstance(status_value, str):
                previous_status = status_value
            verified_before_value = timestamping.get("verified_before")
            if isinstance(verified_before_value, str) and verified_before_value:
                previous_verified_before = verified_before_value

    expected_digest = _root_digest(root)
    existing_detached: DetachedTimestampFile | None = None
    if ots_path.exists():
        try:
            loaded = _load_detached_timestamp(ots_path)
        except Exception:
            loaded = None
        if loaded is not None and loaded.file_digest == expected_digest:
            existing_detached = loaded

    existing_result: TimestampingResult | None = None
    if existing_detached is not None:
        existing_result = _timestamping_result_from_detached(
            detached=existing_detached,
            ots_path=ots_path,
            previous_status=previous_status,
            previous_verified_before=previous_verified_before,
            settings=settings,
            cache_dir=cache_dir,
        )

    if settings.audit_timestamp_provider == "none":
        return existing_result or _timestamping_placeholder("none")

    if settings.audit_timestamp_provider != "opentimestamps":
        raise ValueError(f"Unsupported audit timestamp provider: {settings.audit_timestamp_provider}")

    if session is not None:
        entity_id = await _anchor_entity_id(session, day)
        await append_evidence(
            session=session,
            event_type="anchor_publish_attempted",
            entity_type="daily_anchor",
            entity_id=entity_id,
            payload={
                "day": day.isoformat(),
                "merkle_root": root,
                "provider": settings.audit_timestamp_provider,
            },
        )
    else:
        from uuid import NAMESPACE_URL, uuid5

        entity_id = uuid5(NAMESPACE_URL, f"daily-anchor:{day.isoformat()}")

    detached = existing_detached
    wrote_file = False
    try:
        create_args = _ots_args(settings, cache_dir=cache_dir, use_bitcoin=False)
        if detached is None:
            detached, merkle_tip = _new_detached_timestamp(root)
            create_timestamp(merkle_tip, create_args.calendar_urls, create_args)
            wrote_file = True

        if detached is not None:
            changed = upgrade_timestamp(detached.timestamp, create_args)
            wrote_file = wrote_file or changed or not ots_path.exists()

        result = (
            _timestamping_result_from_detached(
                detached=detached,
                ots_path=ots_path,
                previous_status=previous_status,
                previous_verified_before=previous_verified_before,
                settings=settings,
                cache_dir=cache_dir,
            )
            if detached is not None
            else None
        )
        if detached is not None and wrote_file and result is not None:
            _store_detached_timestamp(ots_path, detached)
        if result is None:
            result = existing_result or TimestampingResult(
                provider="opentimestamps",
                status="failed",
                ots_proof_path=None,
                verified_before=None,
                bitcoin_block_height=None,
                error_type="NoAttestations",
            )
    except (Exception, SystemExit) as exc:
        result = existing_result or TimestampingResult(
            provider="opentimestamps",
            status="failed",
            ots_proof_path=None,
            verified_before=None,
            bitcoin_block_height=None,
            error_type=type(exc).__name__,
        )
        if existing_detached is None and ots_path.exists():
            ots_path.unlink(missing_ok=True)

    if session is not None:
        anchor_result = await session.execute(select(DailyAnchor).where(DailyAnchor.day == day))
        anchor = anchor_result.scalar_one_or_none()
        if anchor is not None:
            anchor.anchor_metadata = {
                **anchor.anchor_metadata,
                "timestamping_provider": result.provider,
                "timestamping_status": result.status,
                "ots_proof_path": result.ots_proof_path,
                "verified_before": result.verified_before,
                "bitcoin_block_height": result.bitcoin_block_height,
            }
        event_type = "anchor_publish_succeeded" if result.status in {"stamped", "verified"} else "anchor_publish_failed"
        payload = {
            "day": day.isoformat(),
            "merkle_root": root,
            "provider": result.provider,
            "status": result.status,
        }
        if result.ots_proof_path is not None:
            payload["ots_proof_path"] = result.ots_proof_path
        if result.error_type is not None:
            payload["error_type"] = result.error_type
        await append_evidence(
            session=session,
            event_type=event_type,
            entity_type="daily_anchor",
            entity_id=entity_id,
            payload=payload,
        )
    return result


async def _anchor_entity_id(session: AsyncSession, day: date) -> UUID:
    """Resolve a stable entity_id for anchoring evidence entries.

    Reuses the entity_id from the anchor_computed event for this day,
    so all anchoring events for the same day share a consistent ID.
    """
    from uuid import NAMESPACE_URL, uuid5

    result = await session.execute(
        select(EvidenceLogEntry.entity_id)
        .where(EvidenceLogEntry.event_type == "anchor_computed")
        .order_by(EvidenceLogEntry.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    return uuid5(NAMESPACE_URL, f"daily-anchor:{day.isoformat()}")

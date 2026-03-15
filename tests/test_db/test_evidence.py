from __future__ import annotations

import asyncio
import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from anyio import Path as AsyncPath
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import Settings
from src.db.anchoring import (
    DailyAnchor,
    TimestampingResult,
    compute_daily_merkle_root,
    export_daily_audit_bundle,
    publish_daily_audit_bundle_metadata,
    publish_daily_merkle_root,
)
from src.db.evidence import (
    EVENT_CATALOG,
    GENESIS_PREV_HASH,
    VALID_EVENT_TYPES,
    EvidenceLogEntry,
    append_evidence,
    apply_visibility_tier,
    canonical_json,
    compute_entry_hash,
    generate_receipt_token,
    strip_evidence_pii,
    verify_chain,
    verify_receipt_token,
)
from src.models.vote import VotingCycle


def _settings(**overrides: str) -> Settings:
    defaults = {
        "database_url": "postgresql+asyncpg://collective:pw@localhost:5432/collective_will",
        "app_public_base_url": "https://collectivewill.org",
        "anthropic_api_key": "x",
        "openai_api_key": "x",
        "deepseek_api_key": "x",
        "evolution_api_key": "x",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_append_single_entry_hash_and_prev_hash(db_session: AsyncSession) -> None:
    entity_id = uuid4()
    entry = await append_evidence(
        db_session, "user_verified", "user", entity_id, {"method": "email_magic_link"}
    )
    await db_session.commit()

    assert entry.prev_hash == GENESIS_PREV_HASH
    expected = compute_entry_hash(
        timestamp_iso=entry.timestamp.astimezone(UTC).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        event_type=entry.event_type,
        entity_type=entry.entity_type,
        entity_id=str(entry.entity_id),
        payload=entry.payload,
        prev_hash=entry.prev_hash,
    )
    assert entry.hash == expected


@pytest.mark.asyncio
async def test_chain_linking_and_verification(db_session: AsyncSession) -> None:
    for idx in range(5):
        await append_evidence(
            db_session,
            "submission_received",
            "submission",
            uuid4(),
            {"idx": idx},
        )
    await db_session.commit()

    result = await db_session.execute(select(EvidenceLogEntry).order_by(EvidenceLogEntry.id))
    entries = list(result.scalars().all())
    assert entries[0].prev_hash == GENESIS_PREV_HASH
    for idx in range(1, len(entries)):
        assert entries[idx].prev_hash == entries[idx - 1].hash

    valid, checked = await verify_chain(db_session)
    assert valid is True
    assert checked == 5


@pytest.mark.asyncio
async def test_verify_chain_detects_payload_tamper(db_session: AsyncSession) -> None:
    first = await append_evidence(db_session, "user_verified", "user", uuid4(), {"a": 1})
    await append_evidence(db_session, "submission_received", "submission", uuid4(), {"b": 2})
    await db_session.commit()

    await db_session.execute(
        update(EvidenceLogEntry)
        .where(EvidenceLogEntry.id == first.id)
        .values(payload={"a": 999})
    )
    await db_session.commit()
    db_session.expire_all()
    valid, _ = await verify_chain(db_session)
    assert valid is False


@pytest.mark.asyncio
async def test_verify_chain_detects_metadata_tamper(db_session: AsyncSession) -> None:
    first = await append_evidence(db_session, "user_verified", "user", uuid4(), {"a": 1})
    await append_evidence(db_session, "submission_received", "submission", uuid4(), {"b": 2})
    await db_session.commit()

    await db_session.execute(
        update(EvidenceLogEntry)
        .where(EvidenceLogEntry.id == first.id)
        .values(event_type="vote_cast")
    )
    await db_session.commit()
    db_session.expire_all()
    valid, _ = await verify_chain(db_session)
    assert valid is False


@pytest.mark.asyncio
async def test_all_valid_event_types_accepted(db_session: AsyncSession) -> None:
    for event_type in sorted(VALID_EVENT_TYPES):
        await append_evidence(db_session, event_type, "test_entity", uuid4(), {"ok": True})
    await db_session.commit()

    valid, checked = await verify_chain(db_session)
    assert valid is True
    assert checked == len(VALID_EVENT_TYPES)


@pytest.mark.asyncio
async def test_invalid_event_type_rejected() -> None:
    mock_session = AsyncMock(spec=AsyncSession)
    with pytest.raises(ValueError, match="Invalid event_type"):
        await append_evidence(mock_session, "invalid_type", "x", uuid4(), {})


def test_compute_entry_hash_deterministic() -> None:
    fixed_id = str(uuid4())
    hash_a = compute_entry_hash(
        timestamp_iso="2026-02-20T12:34:56.789Z",
        event_type="user_verified",
        entity_type="user",
        entity_id=fixed_id,
        payload={"z": 1, "a": 2},
        prev_hash=GENESIS_PREV_HASH,
    )
    hash_b = compute_entry_hash(
        timestamp_iso="2026-02-20T12:34:56.789Z",
        event_type="user_verified",
        entity_type="user",
        entity_id=fixed_id,
        payload={"z": 1, "a": 2},
        prev_hash=GENESIS_PREV_HASH,
    )
    assert hash_a == hash_b


def test_canonical_json_sorted_key_invariance() -> None:
    payload_a = {"z": 1, "a": 2}
    payload_b = {"a": 2, "z": 1}
    assert canonical_json(payload_a) == canonical_json(payload_b)


@pytest.mark.asyncio
async def test_concurrent_appends_keep_integrity(db_session: AsyncSession) -> None:
    maker = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    async def _append(idx: int) -> None:
        async with maker() as session:
            await append_evidence(session, "submission_received", "submission", uuid4(), {"i": idx})
            await session.commit()

    await asyncio.gather(_append(1), _append(2))

    valid, checked = await verify_chain(db_session)
    assert valid is True
    assert checked == 2


@pytest.mark.asyncio
async def test_merkle_root_computed_even_when_publish_disabled(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    today_utc = now.date()
    for idx in range(3):
        entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": idx})
        entry.timestamp = now + timedelta(seconds=idx)
    await db_session.commit()

    root = await compute_daily_merkle_root(db_session, today_utc)
    assert root is not None
    anchor = (await db_session.execute(select(DailyAnchor))).scalar_one()
    assert anchor.merkle_root == root

    settings = _settings(audit_timestamp_provider="none")
    result = await publish_daily_merkle_root(root, today_utc, settings)
    assert result is not None
    assert result.status == "disabled"


@pytest.mark.asyncio
async def test_merkle_root_deterministic_for_fixed_entries(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    today_utc = now.date()
    for idx in range(3):
        entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": idx})
        entry.timestamp = now + timedelta(seconds=idx)
    await db_session.commit()

    root1 = await compute_daily_merkle_root(db_session, today_utc)
    assert root1 is not None
    await db_session.commit()

    anchor = (await db_session.execute(select(DailyAnchor).where(DailyAnchor.day == today_utc))).scalar_one()
    assert anchor.merkle_root == root1


@pytest.mark.asyncio
async def test_publish_stores_opentimestamps_metadata_when_enabled(
    tmp_path: Any, db_session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    today_utc = now.date()
    for idx in range(2):
        entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": idx})
        entry.timestamp = now + timedelta(seconds=idx)
    await db_session.commit()

    root = await compute_daily_merkle_root(db_session, today_utc)
    assert root is not None
    await db_session.commit()

    settings = _settings(
        audit_timestamp_provider="opentimestamps",
        audit_bundle_output_dir=str(tmp_path),
    )

    def _fake_create_timestamp(merkle_tip: Any, _calendar_urls: Any, _args: Any) -> None:
        from opentimestamps.core.notary import PendingAttestation

        merkle_tip.attestations.add(PendingAttestation("https://calendar.example"))

    with (
        patch("src.db.anchoring.create_timestamp", side_effect=_fake_create_timestamp),
        patch("src.db.anchoring.upgrade_timestamp", return_value=False),
    ):
        result = await publish_daily_merkle_root(root, today_utc, settings, session=db_session)
        assert result is not None
        assert result.status == "stamped"
        assert result.ots_proof_path is not None
        await db_session.commit()

    anchor = (await db_session.execute(select(DailyAnchor).where(DailyAnchor.day == today_utc))).scalar_one()
    assert anchor.anchor_metadata["timestamping_status"] == "stamped"
    assert await AsyncPath(anchor.anchor_metadata["ots_proof_path"]).exists()


def test_event_catalog_covers_all_valid_types() -> None:
    """Every VALID_EVENT_TYPE must have an EVENT_CATALOG entry."""
    assert set(EVENT_CATALOG.keys()) == VALID_EVENT_TYPES


def test_receipt_token_generation_and_verification() -> None:
    token = generate_receipt_token("abc123hash", "secret-key")
    assert isinstance(token, str)
    assert len(token) == 64
    assert verify_receipt_token("abc123hash", "secret-key", token) is True
    assert verify_receipt_token("abc123hash", "wrong-key", token) is False
    assert verify_receipt_token("different-hash", "secret-key", token) is False


def test_strip_evidence_pii_nested() -> None:
    payload = {
        "status": "ok",
        "user_id": "should-be-stripped",
        "nested": {"email": "secret@example.com", "data": "visible"},
        "list_field": [{"wa_id": "hidden", "info": "shown"}, "plain"],
    }
    result = strip_evidence_pii(payload)
    assert "user_id" not in result
    assert result["status"] == "ok"
    assert "email" not in result["nested"]
    assert result["nested"]["data"] == "visible"
    assert result["list_field"][0]["info"] == "shown"
    assert "wa_id" not in result["list_field"][0]
    assert result["list_field"][1] == "plain"


def test_apply_visibility_tier_hides_delayed_fields() -> None:
    payload = {
        "cycle_id": "some-cycle",
        "selections": [{"cluster_id": "c1", "option_id": "o1"}],
        "approved_cluster_ids": ["c1"],
    }
    active = apply_visibility_tier("vote_cast", payload, cycle_closed=False)
    assert "selections" not in active
    assert "approved_cluster_ids" not in active
    assert active["cycle_id"] == "some-cycle"

    closed = apply_visibility_tier("vote_cast", payload, cycle_closed=True)
    assert "selections" in closed
    assert "approved_cluster_ids" in closed


def test_apply_visibility_tier_strips_pii() -> None:
    payload = {"user_id": "uid", "cluster_id": "cid"}
    result = apply_visibility_tier("policy_endorsed", payload)
    assert "user_id" not in result
    assert result["cluster_id"] == "cid"


@pytest.mark.asyncio
async def test_new_event_types_accepted(db_session: AsyncSession) -> None:
    """All new event types from the audit ledger plan should be accepted."""
    new_types = [
        "submission_not_eligible",
        "submission_rate_limited",
        "endorsement_not_eligible",
        "vote_not_eligible",
        "vote_change_limit_reached",
        "anchor_publish_attempted",
        "anchor_publish_succeeded",
        "anchor_publish_failed",
    ]
    for event_type in new_types:
        await append_evidence(db_session, event_type, "test", uuid4(), {"test": True})
    await db_session.commit()
    valid, checked = await verify_chain(db_session)
    assert valid is True
    assert checked == len(new_types)


@pytest.mark.asyncio
async def test_publish_failure_does_not_erase_local_root(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    today_utc = now.date()
    for idx in range(2):
        entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": idx})
        entry.timestamp = now + timedelta(seconds=idx)
    await db_session.commit()

    root = await compute_daily_merkle_root(db_session, today_utc)
    assert root is not None
    await db_session.commit()

    settings = _settings(audit_timestamp_provider="opentimestamps")

    with patch("src.db.anchoring.create_timestamp", side_effect=SystemExit(1)):
        result = await publish_daily_merkle_root(root, today_utc, settings, session=db_session)
        assert result is not None
        assert result.status == "failed"

    anchor = (await db_session.execute(select(DailyAnchor).where(DailyAnchor.day == today_utc))).scalar_one()
    assert anchor.merkle_root == root
    assert anchor.published_receipt is None


@pytest.mark.asyncio
async def test_export_daily_audit_bundle_deterministic(tmp_path, db_session: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    today_utc = now.date()
    cycle_id = uuid4()
    active_cycle = VotingCycle(
        id=cycle_id,
        started_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        status="active",
        cluster_ids=[],
        total_voters=0,
    )
    db_session.add(active_cycle)

    vote_payload = {
        "user_id": str(uuid4()),
        "cycle_id": str(cycle_id),
        "approved_cluster_ids": [str(uuid4())],
        "selections": [{"cluster_id": str(uuid4()), "option_id": str(uuid4())}],
    }
    vote_entry = await append_evidence(db_session, "vote_cast", "vote", uuid4(), vote_payload)
    vote_entry.timestamp = now
    await db_session.commit()

    out1 = await export_daily_audit_bundle(db_session, today_utc, output_dir=tmp_path / "run1", emit_evidence=False)
    out2 = await export_daily_audit_bundle(db_session, today_utc, output_dir=tmp_path / "run2", emit_evidence=False)
    assert out1 is not None
    assert out2 is not None
    assert out1.bundle_sha256 == out2.bundle_sha256
    assert out1.entry_count == out2.entry_count

    with gzip.open(out1.storage_path, "rt", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert len(rows) == 1
    # Active cycle -> delayed vote fields must remain hidden in exported public bundle.
    assert "selections" not in rows[0]["payload"]
    assert "approved_cluster_ids" not in rows[0]["payload"]
    assert "user_id" not in rows[0]["payload"]


@pytest.mark.asyncio
async def test_export_daily_audit_bundle_emits_evidence_event(tmp_path, db_session: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    today_utc = now.date()
    entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": 1})
    entry.timestamp = now
    await db_session.commit()

    out = await export_daily_audit_bundle(db_session, today_utc, output_dir=tmp_path, emit_evidence=True)
    assert out is not None
    await db_session.commit()

    result = await db_session.execute(
        select(EvidenceLogEntry)
        .where(EvidenceLogEntry.event_type == "audit_bundle_generated")
        .order_by(EvidenceLogEntry.id.desc())
        .limit(1)
    )
    evt = result.scalar_one_or_none()
    assert evt is not None
    assert evt.payload["day"] == today_utc.isoformat()
    assert evt.payload["bundle_sha256"] == out.bundle_sha256
    assert evt.payload["entry_count"] >= 1


@pytest.mark.asyncio
async def test_publish_daily_audit_bundle_metadata_writes_manifest_and_index(
    tmp_path: Any, db_session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    today_utc = now.date()
    entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": 2})
    entry.timestamp = now
    await db_session.commit()

    root = await compute_daily_merkle_root(db_session, today_utc)
    assert root is not None
    bundle = await export_daily_audit_bundle(db_session, today_utc, output_dir=tmp_path, emit_evidence=False)
    assert bundle is not None
    timestamping = TimestampingResult(
        provider="opentimestamps",
        status="stamped",
        ots_proof_path=str(Path(tmp_path) / today_utc.isoformat() / f"audit-{today_utc.isoformat()}.ots"),
        verified_before=None,
        bitcoin_block_height=None,
    )
    manifest_path, index_path = await publish_daily_audit_bundle_metadata(
        db_session,
        day=today_utc,
        merkle_root=root,
        bundle=bundle,
        output_dir=tmp_path,
        timestamping=timestamping,
        emit_evidence=True,
    )
    await db_session.commit()

    manifest = json.loads(await AsyncPath(manifest_path).read_text(encoding="utf-8"))
    assert manifest["day_utc"] == today_utc.isoformat()
    assert manifest["bundle_sha256"] == bundle.bundle_sha256
    assert manifest["daily_merkle_root"] == root
    assert manifest["timestamping"]["provider"] == "opentimestamps"
    assert manifest["timestamping"]["status"] == "stamped"
    assert manifest["timestamping"]["ots_proof_path"] == timestamping.ots_proof_path

    index = json.loads(await AsyncPath(index_path).read_text(encoding="utf-8"))
    assert index["days"][0]["day_utc"] == today_utc.isoformat()
    assert index["days"][0]["bundle_path"] == bundle.storage_path
    assert index["days"][0]["timestamping_status"] == "stamped"
    assert index["days"][0]["ots_proof_path"] == timestamping.ots_proof_path

    result = await db_session.execute(
        select(EvidenceLogEntry)
        .where(EvidenceLogEntry.event_type == "audit_bundle_publish_succeeded")
        .order_by(EvidenceLogEntry.id.desc())
        .limit(1)
    )
    evt = result.scalar_one_or_none()
    assert evt is not None
    assert evt.payload["manifest_path"] == manifest_path
    assert evt.payload["index_path"] == index_path


@pytest.mark.asyncio
async def test_publish_daily_audit_bundle_metadata_emits_failed_event_on_error(
    tmp_path: Any, db_session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    today_utc = now.date()
    entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": 3})
    entry.timestamp = now
    await db_session.commit()

    root = await compute_daily_merkle_root(db_session, today_utc)
    assert root is not None
    bundle = await export_daily_audit_bundle(db_session, today_utc, output_dir=tmp_path, emit_evidence=False)
    assert bundle is not None

    # Corrupt index file to force JSON decode failure in metadata publishing.
    index_path = AsyncPath(str(tmp_path)) / "index.json"
    await index_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        await publish_daily_audit_bundle_metadata(
            db_session,
            day=today_utc,
            merkle_root=root,
            bundle=bundle,
            output_dir=tmp_path,
            timestamping=TimestampingResult(
                provider="opentimestamps",
                status="failed",
                ots_proof_path=None,
                verified_before=None,
                bitcoin_block_height=None,
                error_type="JSONDecodeError",
            ),
            emit_evidence=True,
        )
    await db_session.commit()

    result = await db_session.execute(
        select(EvidenceLogEntry)
        .where(EvidenceLogEntry.event_type == "audit_bundle_publish_failed")
        .order_by(EvidenceLogEntry.id.desc())
        .limit(1)
    )
    evt = result.scalar_one_or_none()
    assert evt is not None
    assert evt.payload["day"] == today_utc.isoformat()
    assert evt.payload["bundle_sha256"] == bundle.bundle_sha256
    assert evt.payload["error_type"] == "JSONDecodeError"

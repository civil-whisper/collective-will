from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import Settings
from src.db.anchoring import DailyAnchor, compute_daily_merkle_root, publish_daily_merkle_root
from src.db.evidence import (
    GENESIS_PREV_HASH,
    VALID_EVENT_TYPES,
    EvidenceLogEntry,
    append_evidence,
    canonical_json,
    compute_entry_hash,
    verify_chain,
)


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
        db_session, "user_created", "user", entity_id, {"email": "hash@example.com"}
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
    first = await append_evidence(db_session, "user_created", "user", uuid4(), {"a": 1})
    await append_evidence(db_session, "user_verified", "user", uuid4(), {"b": 2})
    await db_session.commit()

    await db_session.execute(
        text("UPDATE evidence_log SET payload = :payload WHERE id = :id"),
        {"payload": '{"a":999}', "id": first.id},
    )
    await db_session.commit()
    valid, _ = await verify_chain(db_session)
    assert valid is False


@pytest.mark.asyncio
async def test_verify_chain_detects_metadata_tamper(db_session: AsyncSession) -> None:
    first = await append_evidence(db_session, "user_created", "user", uuid4(), {"a": 1})
    await append_evidence(db_session, "user_verified", "user", uuid4(), {"b": 2})
    await db_session.commit()

    await db_session.execute(
        text("UPDATE evidence_log SET event_type = 'vote_cast' WHERE id = :id"),
        {"id": first.id},
    )
    await db_session.commit()
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
        event_type="user_created",
        entity_type="user",
        entity_id=fixed_id,
        payload={"z": 1, "a": 2},
        prev_hash=GENESIS_PREV_HASH,
    )
    hash_b = compute_entry_hash(
        timestamp_iso="2026-02-20T12:34:56.789Z",
        event_type="user_created",
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
    for idx in range(3):
        entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": idx})
        entry.timestamp = now + timedelta(seconds=idx)
    await db_session.commit()

    root = await compute_daily_merkle_root(db_session, date.today())
    assert root is not None
    anchor = (await db_session.execute(select(DailyAnchor))).scalar_one()
    assert anchor.merkle_root == root

    settings = _settings()
    assert settings.witness_publish_enabled is False
    assert await publish_daily_merkle_root(root, date.today(), settings) is None


@pytest.mark.asyncio
async def test_merkle_root_deterministic_for_fixed_entries(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for idx in range(3):
        entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": idx})
        entry.timestamp = now + timedelta(seconds=idx)
    await db_session.commit()

    root1 = await compute_daily_merkle_root(db_session, date.today())
    root2 = await compute_daily_merkle_root(db_session, date.today())
    assert root1 is not None
    assert root1 == root2


@pytest.mark.asyncio
async def test_publish_stores_receipt_when_enabled(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for idx in range(2):
        entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": idx})
        entry.timestamp = now + timedelta(seconds=idx)
    await db_session.commit()

    root = await compute_daily_merkle_root(db_session, date.today())
    assert root is not None
    await db_session.commit()

    settings = _settings(witness_publish_enabled="true", witness_api_key="test-key")

    mock_response = AsyncMock()
    mock_response.json.return_value = {"id": "receipt-123"}
    mock_response.raise_for_status = lambda: None

    with patch("src.db.anchoring.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        receipt = await publish_daily_merkle_root(root, date.today(), settings, session=db_session)
        assert receipt == "receipt-123"
        await db_session.commit()

    anchor = (await db_session.execute(select(DailyAnchor).where(DailyAnchor.day == date.today()))).scalar_one()
    assert anchor.published_receipt == "receipt-123"


@pytest.mark.asyncio
async def test_publish_failure_does_not_erase_local_root(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for idx in range(2):
        entry = await append_evidence(db_session, "candidate_created", "candidate", uuid4(), {"i": idx})
        entry.timestamp = now + timedelta(seconds=idx)
    await db_session.commit()

    root = await compute_daily_merkle_root(db_session, date.today())
    assert root is not None
    await db_session.commit()

    settings = _settings(witness_publish_enabled="true", witness_api_key="test-key")

    with patch("src.db.anchoring.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("network failure")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with pytest.raises(Exception, match="network failure"):
            await publish_daily_merkle_root(root, date.today(), settings, session=db_session)

    anchor = (await db_session.execute(select(DailyAnchor).where(DailyAnchor.day == date.today()))).scalar_one()
    assert anchor.merkle_root == root
    assert anchor.published_receipt is None

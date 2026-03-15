from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.main import app
from src.db.connection import get_db
from src.models.submission import Submission
from src.models.user import User
from src.models.vote import Vote
from src.security.web_auth import create_web_access_token


def _make_user(**overrides: Any) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = overrides.get("id", uuid4())
    user.email = overrides.get("email", "test@example.com")
    user.email_verified = overrides.get("email_verified", True)
    return user


def _make_submission(**overrides: Any) -> MagicMock:
    sub = MagicMock(spec=Submission)
    sub.id = overrides.get("id", uuid4())
    sub.raw_text = overrides.get("raw_text", "My concern")
    sub.status = overrides.get("status", "pending")
    sub.hash = overrides.get("hash", "abc123")
    sub.user_id = overrides.get("user_id", uuid4())
    sub.created_at = overrides.get("created_at", datetime.now(UTC))
    return sub


def _make_vote(**overrides: Any) -> MagicMock:
    vote = MagicMock(spec=Vote)
    vote.id = overrides.get("id", uuid4())
    vote.cycle_id = overrides.get("cycle_id", uuid4())
    vote.user_id = overrides.get("user_id", uuid4())
    vote.created_at = overrides.get("created_at", datetime.now(UTC))
    return vote


def _make_evidence_entry(**overrides: Any) -> MagicMock:
    entry = MagicMock()
    entry.id = overrides.get("id", 1)
    entry.timestamp = overrides.get("timestamp", datetime.now(UTC))
    entry.event_type = overrides.get("event_type", "policy_endorsed")
    entry.entity_type = overrides.get("entity_type", "policy_endorsement")
    entry.entity_id = overrides.get("entity_id", uuid4())
    entry.payload = overrides.get("payload", {})
    entry.hash = overrides.get("hash", "hash123")
    entry.prev_hash = overrides.get("prev_hash", "prevhash")
    return entry


def _session_returning_user_then(user: MagicMock | None, second_scalars: list[Any]) -> AsyncMock:
    """Build a mock session where the first query returns a user, the second returns scalars."""
    session = AsyncMock()
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    items_result = MagicMock()
    items_result.scalars.return_value = MagicMock(all=MagicMock(return_value=second_scalars))

    session.execute.side_effect = [user_result, items_result]
    return session


def _auth_headers(email: str = "test@example.com") -> dict[str, str]:
    token = create_web_access_token(email=email)
    return {"Authorization": f"Bearer {token}"}


class TestListSubmissions:
    def test_returns_401_without_user_header(self) -> None:
        session = AsyncMock()
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/user/dashboard/submissions")
            assert response.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_401_for_unknown_user(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get(
                "/user/dashboard/submissions",
                headers=_auth_headers("unknown@example.com"),
            )
            assert response.status_code == 401
            assert "unknown user" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_empty_submissions(self) -> None:
        user = _make_user()
        session = _session_returning_user_then(user, [])
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get(
                "/user/dashboard/submissions",
                headers=_auth_headers(),
            )
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_submissions_list(self) -> None:
        user = _make_user()
        sid = uuid4()
        subs = [_make_submission(id=sid, raw_text="Fix roads", status="processed", hash="h1")]
        session = _session_returning_user_then(user, subs)
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get(
                "/user/dashboard/submissions",
                headers=_auth_headers(),
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == str(sid)
            assert data[0]["raw_text"] == "Fix roads"
            assert data[0]["status"] == "processed"
            assert data[0]["hash"] == "h1"
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestListVotes:
    def test_returns_401_without_user_header(self) -> None:
        session = AsyncMock()
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/user/dashboard/votes")
            assert response.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_empty_votes(self) -> None:
        user = _make_user()
        session = _session_returning_user_then(user, [])
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get(
                "/user/dashboard/votes",
                headers=_auth_headers(),
            )
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_votes_list(self) -> None:
        user = _make_user()
        vid = uuid4()
        cid = uuid4()
        votes = [_make_vote(id=vid, cycle_id=cid)]
        session = _session_returning_user_then(user, votes)
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get(
                "/user/dashboard/votes",
                headers=_auth_headers(),
            )
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == str(vid)
            assert data[0]["cycle_id"] == str(cid)
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestOpenDispute:
    def test_returns_401_without_user_header(self) -> None:
        session = AsyncMock()
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.post(f"/user/dashboard/disputes/{uuid4()}")
            assert response.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestVerifyReceipt:
    def test_returns_404_for_missing_receipt(self, tmp_path: Path) -> None:
        user = _make_user()
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [user_result, entry_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch("src.api.routes.user.get_settings") as mock_settings:
                mock_settings.return_value.audit_bundle_output_dir = str(tmp_path)
                client = TestClient(app)
                response = client.get(
                    "/user/dashboard/receipts/hash123/verify",
                    headers=_auth_headers(),
                )
                assert response.status_code == 404
                assert response.json()["detail"] == "receipt not found"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_recorded_when_not_yet_published(self, tmp_path: Path) -> None:
        user = _make_user()
        entry = _make_evidence_entry(
            payload={"user_id": str(user.id), "cluster_id": str(uuid4())},
            hash="hash-recorded",
        )
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry
        session.execute.side_effect = [user_result, entry_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch("src.api.routes.user.get_settings") as mock_settings:
                mock_settings.return_value.audit_bundle_output_dir = str(tmp_path)
                client = TestClient(app)
                response = client.get(
                    f"/user/dashboard/receipts/{entry.hash}/verify",
                    headers=_auth_headers(),
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "recorded"
                assert data["receipt_valid"] is True
                assert data["entry_found"] is True
                assert data["included_in_public_bundle"] is False
                assert data["bundle_hash_matches_manifest"] is False
                assert data["ots_proof_present"] is False
                expected_bundle_url = (
                    f"/analytics/audit-bundles/{entry.timestamp.date().isoformat()}/bundle"
                )
                assert data["download_urls"]["bundle"].endswith(expected_bundle_url)
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_published_when_bundle_and_manifest_match(self, tmp_path: Path) -> None:
        user = _make_user()
        ts = datetime.now(UTC)
        entry = _make_evidence_entry(
            timestamp=ts,
            payload={"user_id": str(user.id), "cluster_id": str(uuid4())},
            hash="hash-published",
        )
        day = ts.date().isoformat()
        day_dir = tmp_path / day
        day_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = day_dir / f"audit-{day}.jsonl.gz"
        bundle_row = {
            "id": entry.id,
            "timestamp": ts.isoformat(),
            "event_type": entry.event_type,
            "entity_type": entry.entity_type,
            "entity_id": str(entry.entity_id),
            "payload": {"cluster_id": entry.payload["cluster_id"]},
            "hash": entry.hash,
            "prev_hash": entry.prev_hash,
        }
        with gzip.open(bundle_path, "wt", encoding="utf-8") as handle:
            handle.write(json.dumps(bundle_row, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            handle.write("\n")
        bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        manifest_path = day_dir / f"manifest-{day}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "day_utc": day,
                    "bundle_sha256": bundle_sha256,
                    "timestamping": {
                        "provider": "opentimestamps",
                        "status": "pending",
                        "ots_proof_path": None,
                        "verified_before": None,
                        "bitcoin_block_height": None,
                    },
                }
            ),
            encoding="utf-8",
        )

        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry
        session.execute.side_effect = [user_result, entry_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch("src.api.routes.user.get_settings") as mock_settings:
                mock_settings.return_value.audit_bundle_output_dir = str(tmp_path)
                client = TestClient(app)
                response = client.get(
                    f"/user/dashboard/receipts/{entry.hash}/verify",
                    headers=_auth_headers(),
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "published"
                assert data["included_in_public_bundle"] is True
                assert data["bundle_hash_matches_manifest"] is True
                assert data["ots_proof_present"] is False
                assert data["ots_verified"] is False
                assert data["download_urls"]["manifest"].endswith(f"/analytics/audit-bundles/{day}/manifest")
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_verified_when_manifest_has_verified_ots(self, tmp_path: Path) -> None:
        user = _make_user()
        ts = datetime.now(UTC)
        entry = _make_evidence_entry(
            timestamp=ts,
            payload={"user_id": str(user.id), "cluster_id": str(uuid4())},
            hash="hash-verified",
        )
        day = ts.date().isoformat()
        day_dir = tmp_path / day
        day_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = day_dir / f"audit-{day}.jsonl.gz"
        with gzip.open(bundle_path, "wt", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "id": entry.id,
                        "timestamp": ts.isoformat(),
                        "event_type": entry.event_type,
                        "entity_type": entry.entity_type,
                        "entity_id": str(entry.entity_id),
                        "payload": {"cluster_id": entry.payload["cluster_id"]},
                        "hash": entry.hash,
                        "prev_hash": entry.prev_hash,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
            handle.write("\n")
        bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        ots_path = day_dir / f"audit-{day}.ots"
        ots_path.write_text("proof", encoding="utf-8")
        manifest_path = day_dir / f"manifest-{day}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "day_utc": day,
                    "bundle_sha256": bundle_sha256,
                    "timestamping": {
                        "provider": "opentimestamps",
                        "status": "verified",
                        "ots_proof_path": str(ots_path),
                        "verified_before": "2026-03-15T10:00:00.000Z",
                        "bitcoin_block_height": 123,
                    },
                }
            ),
            encoding="utf-8",
        )

        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry
        session.execute.side_effect = [user_result, entry_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch("src.api.routes.user.get_settings") as mock_settings:
                mock_settings.return_value.audit_bundle_output_dir = str(tmp_path)
                client = TestClient(app)
                response = client.get(
                    f"/user/dashboard/receipts/{entry.hash}/verify",
                    headers=_auth_headers(),
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "verified"
                assert data["ots_proof_present"] is True
                assert data["ots_verified"] is True
                assert data["verified_before"] == "2026-03-15T10:00:00.000Z"
                assert data["download_urls"]["ots_proof"].endswith(f"/analytics/audit-bundles/{day}/ots")
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_timestamped_when_ots_exists_but_is_not_verified(self, tmp_path: Path) -> None:
        user = _make_user()
        ts = datetime.now(UTC)
        entry = _make_evidence_entry(
            timestamp=ts,
            payload={"user_id": str(user.id), "cluster_id": str(uuid4())},
            hash="hash-timestamped",
        )
        day = ts.date().isoformat()
        day_dir = tmp_path / day
        day_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = day_dir / f"audit-{day}.jsonl.gz"
        with gzip.open(bundle_path, "wt", encoding="utf-8") as handle:
            handle.write(json.dumps({"hash": entry.hash}) + "\n")
        bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        ots_path = day_dir / f"audit-{day}.ots"
        ots_path.write_text("proof", encoding="utf-8")
        (day_dir / f"manifest-{day}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "day_utc": day,
                    "bundle_sha256": bundle_sha256,
                    "timestamping": {
                        "provider": "opentimestamps",
                        "status": "stamped",
                        "ots_proof_path": str(ots_path),
                        "verified_before": None,
                        "bitcoin_block_height": None,
                    },
                }
            ),
            encoding="utf-8",
        )
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry
        session.execute.side_effect = [user_result, entry_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch("src.api.routes.user.get_settings") as mock_settings:
                mock_settings.return_value.audit_bundle_output_dir = str(tmp_path)
                client = TestClient(app)
                response = client.get(
                    f"/user/dashboard/receipts/{entry.hash}/verify",
                    headers=_auth_headers(),
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "timestamped"
                assert data["ots_proof_present"] is True
                assert data["ots_verified"] is False
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_failed_when_bundle_hash_does_not_match_manifest(self, tmp_path: Path) -> None:
        user = _make_user()
        ts = datetime.now(UTC)
        entry = _make_evidence_entry(
            timestamp=ts,
            payload={"user_id": str(user.id), "cluster_id": str(uuid4())},
            hash="hash-failed",
        )
        day = ts.date().isoformat()
        day_dir = tmp_path / day
        day_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = day_dir / f"audit-{day}.jsonl.gz"
        with gzip.open(bundle_path, "wt", encoding="utf-8") as handle:
            handle.write(json.dumps({"hash": entry.hash}) + "\n")
        (day_dir / f"manifest-{day}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "day_utc": day,
                    "bundle_sha256": "wrong-hash",
                    "timestamping": {
                        "provider": "opentimestamps",
                        "status": "failed",
                        "ots_proof_path": None,
                        "verified_before": None,
                        "bitcoin_block_height": None,
                    },
                }
            ),
            encoding="utf-8",
        )
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry
        session.execute.side_effect = [user_result, entry_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch("src.api.routes.user.get_settings") as mock_settings:
                mock_settings.return_value.audit_bundle_output_dir = str(tmp_path)
                client = TestClient(app)
                response = client.get(
                    f"/user/dashboard/receipts/{entry.hash}/verify",
                    headers=_auth_headers(),
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "failed"
                assert data["included_in_public_bundle"] is True
                assert data["bundle_hash_matches_manifest"] is False
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_400_for_invalid_uuid(self) -> None:
        user = _make_user()
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.post(
                "/user/dashboard/disputes/not-a-uuid",
                headers=_auth_headers(),
            )
            assert response.status_code == 400
            assert "invalid submission id" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_404_for_missing_submission(self) -> None:
        user = _make_user()
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        sub_result = MagicMock()
        sub_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [user_result, sub_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.post(
                f"/user/dashboard/disputes/{uuid4()}",
                headers=_auth_headers(),
            )
            assert response.status_code == 404
            assert "submission not found" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_successful_dispute_opening(self) -> None:
        user = _make_user()
        sub_id = uuid4()
        submission = _make_submission(id=sub_id, user_id=user.id)
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        sub_result = MagicMock()
        sub_result.scalar_one_or_none.return_value = submission
        session.execute.side_effect = [user_result, sub_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch("src.api.routes.user.resolve_submission_dispute", new_callable=AsyncMock) as mock_resolve:
                client = TestClient(app)
                response = client.post(
                    f"/user/dashboard/disputes/{sub_id}",
                    headers=_auth_headers(),
                )
                assert response.status_code == 200
                assert response.json()["status"] == "under_automated_review"
                mock_resolve.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_dispute_calls_resolve(self) -> None:
        user = _make_user()
        sub_id = uuid4()
        submission = _make_submission(id=sub_id, user_id=user.id)
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        sub_result = MagicMock()
        sub_result.scalar_one_or_none.return_value = submission
        session.execute.side_effect = [user_result, sub_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch("src.api.routes.user.resolve_submission_dispute", new_callable=AsyncMock) as mock_resolve:
                client = TestClient(app)
                client.post(
                    f"/user/dashboard/disputes/{sub_id}",
                    headers=_auth_headers(),
                )
                mock_resolve.assert_called_once()
                call_kwargs = mock_resolve.call_args.kwargs
                assert call_kwargs["submission"] == submission
        finally:
            app.dependency_overrides.pop(get_db, None)

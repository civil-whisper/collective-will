from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.main import app
from src.db.connection import get_db
from src.models.submission import Submission
from src.models.user import User
from src.models.vote import Vote


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


def _session_returning_user_then(user: MagicMock | None, second_scalars: list[Any]) -> AsyncMock:
    """Build a mock session where the first query returns a user, the second returns scalars."""
    session = AsyncMock()
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    items_result = MagicMock()
    items_result.scalars.return_value = MagicMock(all=MagicMock(return_value=second_scalars))

    session.execute.side_effect = [user_result, items_result]
    return session


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
                headers={"x-user-email": "unknown@example.com"},
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
                headers={"x-user-email": "test@example.com"},
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
                headers={"x-user-email": "test@example.com"},
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
                headers={"x-user-email": "test@example.com"},
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
                headers={"x-user-email": "test@example.com"},
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
                headers={"x-user-email": "test@example.com"},
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
                headers={"x-user-email": "test@example.com"},
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
            with patch("src.api.routes.user.append_evidence", new_callable=AsyncMock) as mock_evidence:
                client = TestClient(app)
                response = client.post(
                    f"/user/dashboard/disputes/{sub_id}",
                    headers={"x-user-email": "test@example.com"},
                )
                assert response.status_code == 200
                assert response.json()["status"] == "under_automated_review"
                mock_evidence.assert_called_once()
                call_kwargs = mock_evidence.call_args.kwargs
                assert call_kwargs["event_type"] == "cluster_updated"
                assert call_kwargs["entity_type"] == "dispute"
                assert call_kwargs["entity_id"] == sub_id
                assert call_kwargs["payload"]["state"] == "dispute_open"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_dispute_commits_session(self) -> None:
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
            with patch("src.api.routes.user.append_evidence", new_callable=AsyncMock):
                client = TestClient(app)
                client.post(
                    f"/user/dashboard/disputes/{sub_id}",
                    headers={"x-user-email": "test@example.com"},
                )
                session.commit.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_db, None)

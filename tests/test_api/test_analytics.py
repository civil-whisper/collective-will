from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.main import app
from src.db.connection import get_db
from src.db.evidence import EvidenceLogEntry
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate
from src.models.vote import VotingCycle


def _mock_session(scalars: list[Any] | None = None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value = MagicMock(all=MagicMock(return_value=scalars or []))
    session.execute.return_value = result
    return session


def _make_cluster(**overrides: Any) -> MagicMock:
    cluster = MagicMock(spec=Cluster)
    cluster.id = overrides.get("id", uuid4())
    cluster.summary = overrides.get("summary", "Test cluster")
    cluster.policy_topic = overrides.get("policy_topic", "economy")
    cluster.policy_key = overrides.get("policy_key", "test-policy")
    cluster.status = overrides.get("status", "open")
    cluster.member_count = overrides.get("member_count", 5)
    cluster.approval_count = overrides.get("approval_count", 0)
    cluster.created_at = overrides.get("created_at", datetime.now(UTC))
    return cluster


def _make_candidate(**overrides: Any) -> MagicMock:
    candidate = MagicMock(spec=PolicyCandidate)
    candidate.id = overrides.get("id", uuid4())
    candidate.title = overrides.get("title", "Candidate")
    candidate.summary = overrides.get("summary", "Summary")
    candidate.policy_topic = overrides.get("policy_topic", "economy")
    candidate.policy_key = overrides.get("policy_key", "test-policy")
    candidate.confidence = overrides.get("confidence", 0.8)
    candidate.created_at = overrides.get("created_at", datetime.now(UTC))
    return candidate


def _make_evidence_entry(**overrides: Any) -> MagicMock:
    entry = MagicMock(spec=EvidenceLogEntry)
    entry.id = overrides.get("id", 1)
    entry.timestamp = overrides.get("timestamp", datetime(2026, 2, 20, 10, 0, 0, tzinfo=UTC))
    entry.event_type = overrides.get("event_type", "submission_received")
    entry.entity_type = overrides.get("entity_type", "submission")
    entry.entity_id = overrides.get("entity_id", uuid4())
    entry.payload = overrides.get("payload", {"text": "hello"})
    entry.hash = overrides.get("hash", "aaa111")
    entry.prev_hash = overrides.get("prev_hash", "genesis")
    return entry


def _mock_cluster_session(rows: list[tuple[Any, int]]) -> AsyncMock:
    """Mock session for the clusters endpoint which uses result.all() with (Cluster, count) tuples."""
    session = AsyncMock()
    result = MagicMock()
    row_mocks = []
    for cluster, endorsement_count in rows:
        row = MagicMock()
        row.Cluster = cluster
        row.endorsement_count = endorsement_count
        row_mocks.append(row)
    result.all.return_value = row_mocks
    session.execute.return_value = result
    return session


class TestClusters:
    def test_returns_empty_list(self) -> None:
        session = _mock_cluster_session([])
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/clusters")
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_cluster_list(self) -> None:
        cid = uuid4()
        cluster = _make_cluster(
            id=cid, summary="Reform A", policy_topic="governance",
            policy_key="governance-reform", member_count=10,
        )
        session = _mock_cluster_session([(cluster, 3)])
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/clusters")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == str(cid)
            assert data[0]["summary"] == "Reform A"
            assert data[0]["policy_topic"] == "governance"
            assert data[0]["policy_key"] == "governance-reform"
            assert data[0]["status"] == "open"
            assert data[0]["member_count"] == 10
            assert data[0]["approval_count"] == 0
            assert data[0]["endorsement_count"] == 3
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_multiple_clusters(self) -> None:
        clusters = [
            (_make_cluster(summary="A"), 1),
            (_make_cluster(summary="B"), 0),
        ]
        session = _mock_cluster_session(clusters)
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/clusters")
            assert response.status_code == 200
            assert len(response.json()) == 2
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestStats:
    def test_returns_aggregate_stats(self) -> None:
        session = AsyncMock()

        voters_result = MagicMock()
        voters_result.scalar_one.return_value = 3

        submissions_result = MagicMock()
        submissions_result.scalar_one.return_value = 11

        pending_result = MagicMock()
        pending_result.scalar_one.return_value = 4

        cycle = MagicMock(spec=VotingCycle)
        cycle.id = uuid4()
        cycle.started_at = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        cycle.ends_at = datetime(2026, 2, 28, 12, 0, 0, tzinfo=UTC)
        cycle.cluster_ids = [uuid4(), uuid4()]
        cycle_result = MagicMock()
        cycle_result.scalars.return_value = MagicMock(first=MagicMock(return_value=cycle))

        session.execute.side_effect = [voters_result, submissions_result, pending_result, cycle_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["total_voters"] == 3
            assert data["total_submissions"] == 11
            assert data["pending_submissions"] == 4
            assert data["current_cycle"] == str(cycle.id)
            assert data["active_cycle"] is not None
            assert data["active_cycle"]["cluster_count"] == 2
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestUnclustered:
    def test_returns_unclustered_candidates(self) -> None:
        clustered_candidate_id = uuid4()
        unclustered_candidate_id = uuid4()
        candidate = _make_candidate(id=unclustered_candidate_id, title="Housing access")

        session = AsyncMock()

        clusters_result = MagicMock()
        clusters_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[[clustered_candidate_id]])
        )

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        candidates_result = MagicMock()
        candidates_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[candidate]))

        session.execute.side_effect = [clusters_result, count_result, candidates_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/unclustered")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["id"] == str(unclustered_candidate_id)
            assert data["items"][0]["title"] == "Housing access"
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestTopPolicies:
    def test_returns_empty_when_no_tallied_cycles(self) -> None:
        session = _mock_session([])
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/top-policies")
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_sorted_policies(self) -> None:
        cycle = MagicMock(spec=VotingCycle)
        cycle.status = "tallied"
        cycle.results = [
            {"cluster_id": str(uuid4()), "approval_count": 5, "approval_rate": 0.5},
            {"cluster_id": str(uuid4()), "approval_count": 20, "approval_rate": 0.9},
        ]
        session = _mock_session([cycle])
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/top-policies")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["approval_rate"] == 0.9
            assert data[1]["approval_rate"] == 0.5
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_skips_cycles_without_results(self) -> None:
        cycle = MagicMock(spec=VotingCycle)
        cycle.status = "tallied"
        cycle.results = None
        session = _mock_session([cycle])
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/top-policies")
            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_aggregates_across_multiple_cycles(self) -> None:
        cycle1 = MagicMock(spec=VotingCycle)
        cycle1.status = "tallied"
        cycle1.results = [{"cluster_id": "c1", "approval_count": 10, "approval_rate": 0.8}]
        cycle2 = MagicMock(spec=VotingCycle)
        cycle2.status = "tallied"
        cycle2.results = [{"cluster_id": "c2", "approval_count": 15, "approval_rate": 0.95}]
        session = _mock_session([cycle1, cycle2])
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/top-policies")
            data = response.json()
            assert len(data) == 2
            assert data[0]["approval_rate"] == 0.95
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestActiveBallot:
    def test_returns_null_when_no_active_cycle(self) -> None:
        session = AsyncMock()
        cycle_result = MagicMock()
        cycle_result.scalars.return_value = MagicMock(first=MagicMock(return_value=None))
        session.execute.return_value = cycle_result
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/active-ballot")
            assert response.status_code == 200
            assert response.json() is None
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_active_ballot_with_clusters_and_options(self) -> None:
        from datetime import timedelta

        cluster_id = uuid4()
        opt_id = uuid4()
        cycle = MagicMock(spec=VotingCycle)
        cycle.id = uuid4()
        cycle.status = "active"
        cycle.started_at = datetime.now(UTC)
        cycle.ends_at = datetime.now(UTC) + timedelta(hours=48)
        cycle.cluster_ids = [cluster_id]

        cycle_result = MagicMock()
        cycle_result.scalars.return_value = MagicMock(first=MagicMock(return_value=cycle))

        vote_count_result = MagicMock()
        vote_count_result.scalar_one.return_value = 7

        cluster = _make_cluster(id=cluster_id, summary="Reform governance")
        cluster.ballot_question = "Should we reform governance?"
        cluster.ballot_question_fa = "آیا باید حاکمیت را اصلاح کنیم؟"
        clusters_result = MagicMock()
        clusters_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[cluster]))

        opt = MagicMock()
        opt.id = opt_id
        opt.cluster_id = cluster_id
        opt.position = 1
        opt.label = "Option A"
        opt.label_en = "Option A EN"
        opt.description = "Desc A"
        opt.description_en = "Desc A EN"
        options_result = MagicMock()
        options_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[opt]))

        session = AsyncMock()
        session.execute.side_effect = [cycle_result, vote_count_result, clusters_result, options_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/active-ballot")
            assert response.status_code == 200
            data = response.json()
            assert data is not None
            assert data["total_voters"] == 7
            assert len(data["clusters"]) == 1
            c = data["clusters"][0]
            assert c["summary"] == "Reform governance"
            assert c["ballot_question"] == "Should we reform governance?"
            assert len(c["options"]) == 1
            assert c["options"][0]["label"] == "Option A"
            assert c["options"][0]["description"] == "Desc A"
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestEvidence:
    def test_returns_empty_list(self) -> None:
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        entries_result = MagicMock()
        entries_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
        session.execute.side_effect = [count_result, entries_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/evidence")
            assert response.status_code == 200
            data = response.json()
            assert data["entries"] == []
            assert data["total"] == 0
            assert data["page"] == 1
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_returns_formatted_entries(self) -> None:
        eid = uuid4()
        entry = _make_evidence_entry(entity_id=eid, hash="abc123", prev_hash="genesis")
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        entries_result = MagicMock()
        entries_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[entry]))
        session.execute.side_effect = [count_result, entries_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/evidence")
            data = response.json()
            assert len(data["entries"]) == 1
            assert data["entries"][0]["entity_id"] == str(eid)
            assert data["entries"][0]["hash"] == "abc123"
            assert data["entries"][0]["prev_hash"] == "genesis"
            assert data["entries"][0]["event_type"] == "submission_received"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_strips_pii_from_payload(self) -> None:
        eid = uuid4()
        entry = _make_evidence_entry(
            entity_id=eid,
            payload={"status": "accepted", "user_id": "secret-uid", "raw_text": "my concern"},
        )
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        entries_result = MagicMock()
        entries_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[entry]))
        session.execute.side_effect = [count_result, entries_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/evidence")
            payload = response.json()["entries"][0]["payload"]
            assert "user_id" not in payload
            assert payload["status"] == "accepted"
            assert payload["raw_text"] == "my concern"
        finally:
            app.dependency_overrides.pop(get_db, None)


    def test_returns_newest_first_order(self) -> None:
        """Page 1 should contain the most recent entries (desc by id)."""
        older = _make_evidence_entry(id=1, event_type="submission_received")
        newer = _make_evidence_entry(id=2, event_type="candidate_created")
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        entries_result = MagicMock()
        entries_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[newer, older])
        )
        session.execute.side_effect = [count_result, entries_result]
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.get("/analytics/evidence")
            data = response.json()
            assert len(data["entries"]) == 2
            assert data["entries"][0]["id"] == 2
            assert data["entries"][1]["id"] == 1
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestVerifyChain:
    def test_verify_endpoint_returns_result(self) -> None:
        from unittest.mock import patch

        with patch("src.api.routes.analytics.db_verify_chain", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = (True, 5)
            client = TestClient(app)
            response = client.get("/analytics/evidence/verify")
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["entries_checked"] == 5

    def test_verify_endpoint_reports_invalid(self) -> None:
        from unittest.mock import patch

        with patch("src.api.routes.analytics.db_verify_chain", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = (False, 3)
            client = TestClient(app)
            response = client.get("/analytics/evidence/verify")
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["entries_checked"] == 3

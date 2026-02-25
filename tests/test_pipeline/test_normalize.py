"""Tests for hybrid embedding + LLM normalization utilities."""
from __future__ import annotations

import numpy as np

from src.pipeline.normalize import (
    _build_submissions_block,
    _cluster_by_embedding,
    _extract_merges_from_mapping,
    _parse_remap_response,
)


class TestParseRemapResponse:
    def test_simple_mapping(self) -> None:
        raw = '{"key_mapping": {"key-a": "key-b", "key-b": "key-b"}}'
        result = _parse_remap_response(raw)
        assert result == {"key-a": "key-b", "key-b": "key-b"}

    def test_empty_mapping(self) -> None:
        raw = '{"key_mapping": {}}'
        result = _parse_remap_response(raw)
        assert result == {}

    def test_markdown_wrapped(self) -> None:
        raw = '```json\n{"key_mapping": {"a": "b", "b": "b"}}\n```'
        result = _parse_remap_response(raw)
        assert result == {"a": "b", "b": "b"}

    def test_leading_text_before_json(self) -> None:
        raw = 'Here is the result:\n{"key_mapping": {"x": "y", "y": "y"}}'
        result = _parse_remap_response(raw)
        assert result == {"x": "y", "y": "y"}

    def test_new_canonical_key(self) -> None:
        raw = '{"key_mapping": {"old-a": "new-canonical", "old-b": "new-canonical"}}'
        result = _parse_remap_response(raw)
        assert result["old-a"] == "new-canonical"
        assert result["old-b"] == "new-canonical"

    def test_identity_mapping(self) -> None:
        raw = '{"key_mapping": {"keep-me": "keep-me", "also-keep": "also-keep"}}'
        result = _parse_remap_response(raw)
        assert result == {"keep-me": "keep-me", "also-keep": "also-keep"}


class TestExtractMergesFromMapping:
    def test_simple_merge(self) -> None:
        mapping = {"key-a": "key-b", "key-b": "key-b"}
        valid = {"key-a", "key-b"}
        merges = _extract_merges_from_mapping(mapping, valid)
        assert merges == {"key-b": ["key-a"]}

    def test_no_merges_identity(self) -> None:
        mapping = {"key-a": "key-a", "key-b": "key-b"}
        valid = {"key-a", "key-b"}
        merges = _extract_merges_from_mapping(mapping, valid)
        assert merges == {}

    def test_multiple_merge_groups(self) -> None:
        mapping = {"a": "x", "b": "x", "c": "y", "d": "y", "x": "x", "y": "y"}
        valid = {"a", "b", "c", "d", "x", "y"}
        merges = _extract_merges_from_mapping(mapping, valid)
        assert set(merges["x"]) == {"a", "b"}
        assert set(merges["y"]) == {"c", "d"}

    def test_new_canonical_key(self) -> None:
        mapping = {"old-a": "brand-new", "old-b": "brand-new"}
        valid = {"old-a", "old-b"}
        merges = _extract_merges_from_mapping(mapping, valid)
        assert set(merges["brand-new"]) == {"old-a", "old-b"}

    def test_ignores_unknown_keys(self) -> None:
        mapping = {"known": "target", "unknown": "target"}
        valid = {"known"}
        merges = _extract_merges_from_mapping(mapping, valid)
        assert merges == {"target": ["known"]}


class TestBuildSubmissionsBlock:
    def test_single_entry(self) -> None:
        entries = [{"key": "hijab-policy", "topic": "dress-code", "count": 5, "summary": "Policy about hijab"}]
        block = _build_submissions_block(entries)
        assert '"hijab-policy"' in block
        assert '"dress-code"' in block
        assert "5 submissions" in block
        assert "Policy about hijab" in block

    def test_multiple_entries(self) -> None:
        entries = [
            {"key": "key-a", "topic": "topic-1", "count": 10, "summary": "Summary A"},
            {"key": "key-b", "topic": "topic-2", "count": 3, "summary": "Summary B"},
        ]
        block = _build_submissions_block(entries)
        assert "1." in block
        assert "2." in block
        assert '"key-a"' in block
        assert '"key-b"' in block


class TestClusterByEmbedding:
    def test_single_vector(self) -> None:
        embeddings = np.array([[1.0, 0.0, 0.0]])
        labels = _cluster_by_embedding(embeddings)
        assert len(labels) == 1

    def test_identical_vectors_same_cluster(self) -> None:
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ])
        labels = _cluster_by_embedding(embeddings, threshold=0.55)
        assert labels[0] == labels[1] == labels[2]

    def test_orthogonal_vectors_different_clusters(self) -> None:
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        labels = _cluster_by_embedding(embeddings, threshold=0.55)
        assert len(set(labels)) == 3

    def test_similar_vectors_merge(self) -> None:
        v1 = np.array([1.0, 0.1, 0.0])
        v2 = np.array([1.0, 0.15, 0.0])
        v3 = np.array([0.0, 0.0, 1.0])
        embeddings = np.array([v1, v2, v3])
        labels = _cluster_by_embedding(embeddings, threshold=0.55)
        assert labels[0] == labels[1]
        assert labels[0] != labels[2]

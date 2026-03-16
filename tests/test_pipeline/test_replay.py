from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.pipeline.llm import EmbeddingResult, LLMResponse
from src.pipeline.replay import ReplaySubmissionInput, replay_submissions


class FakeReplayRouter:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            option_generation_grounding_enabled=False,
            option_generation_grounding_topics="digital-rights",
        )
        self._canonical_by_text = {
            "Workers should organize coordinated strikes to economically pressure the regime.": {
                "is_valid_policy": True,
                "rejection_reason": None,
                "title": "Domestic economic strike pressure",
                "summary": "Citizens should use labor strikes to economically pressure the Iranian regime.",
                "stance": "support",
                "policy_topic": "economic-resistance",
                "policy_key": "domestic-economic-strike",
                "actor_scope": "domestic-citizens",
                "action_mechanism": "labor-strike",
                "target_scope": "iranian-regime",
                "ballot_readiness": "ballot-ready",
                "ballot_readiness_reason": "This is a concrete civic proposition.",
                "entities": ["labor strikes"],
                "confidence": 0.92,
                "ambiguity_flags": [],
            },
            "Use nationwide labor stoppages so the government loses revenue and leverage.": {
                "is_valid_policy": True,
                "rejection_reason": None,
                "title": "Nationwide labor stoppages",
                "summary": "Nationwide labor stoppages should be used to reduce regime revenue and leverage.",
                "stance": "support",
                "policy_topic": "economic-resistance",
                "policy_key": "domestic-economic-strike",
                "actor_scope": "domestic-citizens",
                "action_mechanism": "labor-strike",
                "target_scope": "iranian-regime",
                "ballot_readiness": "ballot-ready",
                "ballot_readiness_reason": "This is a concrete civic proposition.",
                "entities": ["labor stoppages"],
                "confidence": 0.9,
                "ambiguity_flags": [],
            },
            "Other countries should increase sanctions until the regime changes course.": {
                "is_valid_policy": True,
                "rejection_reason": None,
                "title": "Increase foreign sanctions",
                "summary": "Foreign governments should increase sanctions to pressure the Iranian regime.",
                "stance": "support",
                "policy_topic": "foreign-pressure",
                "policy_key": "foreign-economic-sanctions",
                "actor_scope": "foreign-state",
                "action_mechanism": "economic-sanctions",
                "target_scope": "iranian-regime",
                "ballot_readiness": "needs-refinement",
                "ballot_readiness_reason": "The submissions imply pressure but do not define sanction scope or limits.",
                "entities": ["sanctions"],
                "confidence": 0.84,
                "ambiguity_flags": [],
            },
        }
        self.option_generation_grounding_calls: list[bool] = []

    async def complete(self, *, tier: str, prompt: str, **kwargs: object) -> LLMResponse:
        if tier == "canonicalization":
            marker = "Input: "
            payload = json.loads(prompt[prompt.rfind(marker) + len(marker) :].strip())
            raw_text = payload["raw_text"]
            return LLMResponse(
                text=json.dumps(self._canonical_by_text[raw_text]),
                model="fixture-canonical",
                input_tokens=10,
                output_tokens=10,
                cost_usd=0.0,
            )

        if tier == "english_reasoning":
            if 'Policy discussion: "domestic-economic-strike"' in prompt:
                return LLMResponse(
                    text=json.dumps({
                        "ballot_question": "Adopt coordinated labor strikes to economically pressure the Iranian regime.",
                        "ballot_question_fa": "اعتصاب‌های هماهنگ کارگری برای فشار اقتصادی به حکومت اجرا شود",
                        "summary": "Debate over using coordinated labor strikes as domestic economic pressure.",
                    }),
                    model="fixture-reasoning",
                    input_tokens=10,
                    output_tokens=10,
                    cost_usd=0.0,
                )
            if 'Policy discussion: "foreign-economic-sanctions"' in prompt:
                return LLMResponse(
                    text=json.dumps({
                        "ballot_question": "Further refine whether increased foreign sanctions should advance as a public proposition.",
                        "ballot_question_fa": "مشخص شود آیا افزایش تحریم‌های خارجی باید به عنوان یک پیشنهاد عمومی جلو برود",
                        "summary": "Discussion over whether stronger foreign sanctions should be pursued.",
                    }),
                    model="fixture-reasoning",
                    input_tokens=10,
                    output_tokens=10,
                    cost_usd=0.0,
                )
            if "Create a refinement draft for this cluster." in prompt:
                return LLMResponse(
                    text=json.dumps({
                        "refinement_draft": "Require a public proposal that defines the scope, duration, and legal conditions for any increase in foreign sanctions.",
                        "refinement_draft_fa": "یک پیشنهاد عمومی باید دامنه، مدت و شرایط هر افزایش تحریم خارجی را مشخص کند",
                        "refinement_confidence": 0.61,
                        "requires_clarification": True,
                        "notes": "The direction is clear, but the exact sanction design is still underspecified.",
                    }),
                    model="fixture-reasoning",
                    input_tokens=10,
                    output_tokens=10,
                    cost_usd=0.0,
                )

        if tier == "option_generation":
            self.option_generation_grounding_calls.append(bool(kwargs.get("grounding", False)))
            return LLMResponse(
                text=json.dumps(
                    [
                        {
                            "label": "اعتصاب فراگیر",
                            "label_en": "Broad strike strategy",
                            "description": "اعتصاب گسترده و هماهنگ برای کاهش منابع حکومت، با ریسک فشار اقتصادی بر مردم.",
                            "description_en": "Use broad coordinated strikes to reduce regime resources, with the trade-off of economic pressure on the public.",
                        },
                        {
                            "label": "اعتصاب هدفمند",
                            "label_en": "Targeted strike strategy",
                            "description": "اعتصاب‌های محدود و هدفمند در بخش‌های کلیدی، با اثر کمتر بر زندگی روزمره اما فشار کمتر.",
                            "description_en": "Use narrower strikes in key sectors, reducing spillover on daily life but also lowering overall pressure.",
                        },
                    ]
                ),
                model="fixture-options",
                input_tokens=10,
                output_tokens=10,
                cost_usd=0.0,
            )

        raise AssertionError(f"Unexpected tier={tier} prompt={prompt[:120]}")

    async def complete_with_model(self, *, model: str, prompt: str, **kwargs: object) -> LLMResponse:
        return await self.complete(tier="option_generation", prompt=prompt, **kwargs)

    async def embed(self, texts: list[str], timeout_s: float | None = None) -> EmbeddingResult:
        vectors: list[list[float]] = []
        for text in texts:
            if "sanctions" in text.lower():
                vectors.append([0.0, 1.0, 0.0])
            elif "stoppages" in text.lower():
                vectors.append([0.99, 0.01, 0.0])
            else:
                vectors.append([1.0, 0.0, 0.0])
        return EmbeddingResult(vectors=vectors, model="fixture-embedding", provider="fixture")


@pytest.mark.asyncio
async def test_replay_submissions_generates_cluster_artifacts() -> None:
    submissions = [
        ReplaySubmissionInput(
            raw_text="Workers should organize coordinated strikes to economically pressure the regime.",
            language="en",
            source_submission_id="sub-1",
        ),
        ReplaySubmissionInput(
            raw_text="Use nationwide labor stoppages so the government loses revenue and leverage.",
            language="en",
            source_submission_id="sub-2",
        ),
        ReplaySubmissionInput(
            raw_text="Other countries should increase sanctions until the regime changes course.",
            language="en",
            source_submission_id="sub-3",
        ),
    ]

    router = FakeReplayRouter()
    report = await replay_submissions(submissions=submissions, llm_router=router)  # type: ignore[arg-type]

    assert report["submission_count"] == 3
    assert report["candidate_count"] == 3
    assert report["rejected_count"] == 0
    assert report["cluster_count"] == 2

    clusters_by_key = {cluster["policy_key"]: cluster for cluster in report["clusters"]}
    strike_cluster = clusters_by_key["domestic-economic-strike"]
    sanctions_cluster = clusters_by_key["foreign-economic-sanctions"]

    assert strike_cluster["member_count"] == 2
    assert strike_cluster["ballot_question"] == "Adopt coordinated labor strikes to economically pressure the Iranian regime."
    assert len(strike_cluster["options"]) == 2
    assert strike_cluster["refinement_draft"] is None

    assert sanctions_cluster["member_count"] == 1
    assert sanctions_cluster["refinement_requires_clarification"] is True
    assert sanctions_cluster["refinement_draft"] is not None
    assert sanctions_cluster["options"] == []
    assert router.option_generation_grounding_calls == [False]

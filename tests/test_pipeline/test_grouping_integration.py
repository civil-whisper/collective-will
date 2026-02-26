"""Grouping integration test: 100+ submissions → serial canonicalize → interleaved normalize → verify grouping.

Tests the full LLM-driven policy grouping pipeline with realistic submissions
across 5 policy discussions plus outliers.

Runs in 4 rounds of 25 submissions each, with normalization after every round.

First run  (GENERATE_GROUPING_CACHE=1): calls real LLM APIs, saves to cache
Subsequent runs: replays from cache, finishes in seconds.

Usage:
    # Generate cache (one-time):
    GENERATE_GROUPING_CACHE=1 uv run pytest tests/test_pipeline/test_grouping_integration.py -s

    # Run from cache (free, fast):
    uv run pytest tests/test_pipeline/test_grouping_integration.py -s
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import numpy as np
import pytest

from src.config import Settings, get_settings
from src.pipeline.canonicalize import CanonicalizationRejection, canonicalize_single
from src.pipeline.embeddings import prepare_text_for_embedding
from src.pipeline.llm import EmbeddingResult, LLMResponse, LLMRouter
from src.pipeline.normalize import (
    _REMAP_PROMPT_TEMPLATE,
    _REMAP_SYSTEM_PROMPT,
    COSINE_SIMILARITY_THRESHOLD,
    _build_submissions_block,
    _cluster_by_embedding,
    _extract_merges_from_mapping,
    _parse_remap_response,
)

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent.parent / "fixtures" / "grouping_cache.json.gz"
GENERATE_MODE = bool(os.getenv("GENERATE_GROUPING_CACHE"))
PROJECT_ROOT = Path(__file__).parent.parent.parent

ROUND_SIZE = 25

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not GENERATE_MODE and not CACHE_PATH.exists(),
        reason="Grouping cache not found. Run with GENERATE_GROUPING_CACHE=1 to generate.",
    ),
]

# ---------------------------------------------------------------------------
# Submission data: 5 groups × ~18 + ~10 outliers ≈ 100
# ---------------------------------------------------------------------------

GROUP_HIJAB = "hijab-dress-code"
GROUP_INTERNET = "internet-censorship"
GROUP_DEATH_PENALTY = "death-penalty"
GROUP_LANGUAGE_RIGHTS = "ethnic-language-rights"
GROUP_PRIVATIZATION = "state-privatization"
GROUP_OUTLIER = "outlier"

EXPECTED_MAIN_GROUPS = {
    GROUP_HIJAB,
    GROUP_INTERNET,
    GROUP_DEATH_PENALTY,
    GROUP_LANGUAGE_RIGHTS,
    GROUP_PRIVATIZATION,
}

SUBMISSIONS: list[dict[str, str]] = [
    # --- Group 1: Mandatory hijab / dress code (~18) ---
    {
        "text": "حجاب اجباری باید لغو بشه. هر زنی باید خودش تصمیم بگیره چی بپوشه.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "The mandatory hijab law must be abolished immediately. Personal clothing is a basic right.",
        "language": "en",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "من معتقدم حجاب باید اختیاری باشه ولی با احترام به فرهنگ. یه حد وسطی لازمه.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "What should happen with the hijab policy after political transition? Should it remain mandatory?",
        "language": "en",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "پوشش اجباری زنان مغایر با حقوق بشره. قوانین لباس باید تغییر کنه.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "I support maintaining modest dress codes in public spaces. It preserves our cultural values.",
        "language": "en",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "آیا بعد از تغییر حکومت، قوانین پوشش تغییر می‌کنه؟ نظر مردم چیه؟",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "Enforce modest clothing standards but stop arresting women. Education instead of punishment.",
        "language": "en",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "گشت ارشاد باید منحل بشه. نباید به خاطر لباس کسی رو بازداشت کرد.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "من نگرانم اگه حجاب اختیاری بشه، فشار اجتماعی روی زنان محجبه بیشتر بشه.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "How do citizens feel about the current dress code enforcement? It needs a referendum.",
        "language": "en",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "قانون حجاب اجباری ربطی به دین نداره. این یه ابزار کنترل سیاسیه.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "Women's dress code policy should protect freedom while respecting diverse beliefs in society.",
        "language": "en",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "باید یه رفراندوم درباره قانون پوشش برگزار بشه. بذارید مردم تصمیم بگیرن.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "I think the hijab debate is overblown. Focus should be on economic issues first.",
        "language": "en",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "لغو حجاب اجباری اولین قدم به سوی آزادی زنان در ایران است.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "هر شهروندی باید آزادی انتخاب پوشش داشته باشه، چه حجاب بخواد چه نخواد.",
        "language": "fa",
        "expected_group": GROUP_HIJAB,
    },
    {
        "text": "Dress code regulations should be reformed, not enforced through morality police patrols.",
        "language": "en",
        "expected_group": GROUP_HIJAB,
    },
    # --- Group 2: Internet censorship / content filtering (~18) ---
    {
        "text": "فیلترینگ اینترنت باید برداشته بشه. دسترسی آزاد به اطلاعات حق مردمه.",
        "language": "fa",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "Internet censorship in Iran is destroying our tech industry and isolating us from the world.",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "من فکر می‌کنم فیلترینگ سیاسی اینترنت باید برداشته بشه ولی محتوای نامناسب برای کودکان فیلتر بمونه.",
        "language": "fa",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "Should internet filtering remain after regime change? We need a clear digital rights framework.",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "VPN استفاده می‌کنم ولی سرعت اینترنت خیلی کمه. فیلترینگ اقتصاد دیجیتال رو نابود کرده.",
        "language": "fa",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "I support some content regulation online but blanket censorship of social media is wrong.",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "قطع اینترنت در اعتراضات نقض حقوق بشره. هیچ دولتی حق قطع ارتباطات مردم رو نداره.",
        "language": "fa",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "Internet shutdowns during protests must be constitutionally banned in the new government.",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "توییتر و یوتوب و اینستاگرام باید آزاد باشه. دولت نباید تصمیم بگیره مردم چی ببینن.",
        "language": "fa",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "A free and open internet is fundamental for democracy. End all political content filtering.",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "سانسور اینترنت مانع پیشرفت علمی و آموزشی کشوره. دانشجوها به منابع دسترسی ندارن.",
        "language": "fa",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "How should a democratic Iran handle online content? Complete freedom or some regulation?",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "فیلترینگ فقط یه ابزار سرکوب سیاسیه. هیچ فایده امنیتی واقعی نداره.",
        "language": "fa",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "We need net neutrality laws and anti-censorship constitutional protections.",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    {"text": "اینترنت ملی یه ایده خطرناکه. باید جلوش رو گرفت.", "language": "fa", "expected_group": GROUP_INTERNET},
    {
        "text": "Access to global internet should be a constitutional right for every Iranian citizen.",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "دسترسی به اینترنت آزاد برای کسب‌وکارهای آنلاین حیاتیه. فیلترینگ اشتغال‌زایی رو کشته.",
        "language": "fa",
        "expected_group": GROUP_INTERNET,
    },
    {
        "text": "The tech sector cannot grow under censorship. Free internet is an economic necessity.",
        "language": "en",
        "expected_group": GROUP_INTERNET,
    },
    # --- Group 3: Death penalty / capital punishment (~18) ---
    {
        "text": "اعدام باید کاملاً لغو بشه. هیچ دولتی حق گرفتن جان کسی رو نداره.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "The death penalty should be abolished. It is a cruel and irreversible punishment.",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "من فکر می‌کنم اعدام برای قتل عمد باید بمونه ولی برای جرائم مواد مخدر نه.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "Should capital punishment continue for drug offenses? The current laws are too harsh.",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "اعدام در ملأ عام یه عمل وحشیانه‌ست که باید فوراً متوقف بشه.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "I believe the death penalty deters serious crime and should remain for murder cases only.",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "آمار نشون میده اعدام بازدارندگی نداره. باید حبس ابد جایگزین بشه.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "Public executions are a violation of human dignity. They traumatize entire communities.",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "حکم قصاص نفس باید بازبینی بشه. خانواده مقتول نباید تنها تصمیم‌گیرنده باشه.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "What alternatives to capital punishment should a democratic Iran implement?",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "ایران بیشترین اعدام سرانه رو داره. این یه بحران حقوق بشریه.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "Juvenile executions must stop immediately. Iran is one of the few countries still doing this.",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "اعدام برای جرائم سیاسی و عقیدتی کاملاً غیرقابل قبوله.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "Replace death penalty with life imprisonment. The justice system makes too many errors.",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "قوه قضاییه باید اصلاح بشه و مجازات اعدام به حداقل برسه.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "Capital punishment for drug crimes is disproportionate and targets the poorest citizens.",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "باید یه بحث ملی درباره اعدام داشته باشیم. نظر مردم مهمه.",
        "language": "fa",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    {
        "text": "The death penalty debate needs public input. Put it to a national vote.",
        "language": "en",
        "expected_group": GROUP_DEATH_PENALTY,
    },
    # --- Group 4: Ethnic minority language rights (~18) ---
    {
        "text": "زبان‌های اقوام مثل کردی و آذری باید در مدارس تدریس بشه.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "Kurdish, Azerbaijani, Balochi and Arabic should be recognized as official regional languages.",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "حق آموزش به زبان مادری یه حق اساسیه. بچه‌های کرد و ترک باید به زبان خودشون درس بخونن.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "Should minority languages have official status in their provinces? I think yes.",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "فارسی زبان ملی باشه ولی زبان‌های محلی هم باید حمایت بشن. تنوع زبانی ثروته.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "I worry that making multiple languages official will divide the country. One language unites us.",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "بلوچ‌ها و عرب‌ها و ترکمن‌ها سال‌هاست از تبعیض زبانی رنج می‌برن. باید تمام بشه.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "Ethnic language education should be funded by the central government in all provinces.",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "آذری‌ها حق دارن که رسانه و تلویزیون به زبان ترکی داشته باشن.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "A new constitution must guarantee the right to education in one's mother tongue.",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "تبعیض زبانی باعث شکاف اجتماعی شده. باید همه زبان‌ها رسمیت پیدا کنن.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "Language rights are human rights. Banning minority language instruction is cultural suppression.",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "کردی و ترکی و عربی باید در اسناد رسمی استانی قابل استفاده باشن.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "We should have bilingual education: Persian plus the regional language in each province.",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "زبان‌های اقلیت در خطر نابودی هستن. دولت باید برنامه حفاظت از زبان داشته باشه.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "Why can't government services be offered in Kurdish in Kurdistan province?",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "حق تحصیل به زبان مادری باید در قانون اساسی جدید تضمین بشه.",
        "language": "fa",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    {
        "text": "State television should broadcast in all major ethnic languages, not just Persian.",
        "language": "en",
        "expected_group": GROUP_LANGUAGE_RIGHTS,
    },
    # --- Group 5: Privatization of state enterprises (~18) ---
    {
        "text": "شرکت‌های دولتی باید خصوصی‌سازی بشن. دولت کارایی لازم رو نداره.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "State-owned enterprises should be fully privatized to boost economic efficiency.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "خصوصی‌سازی بدون نظارت فقط به نفع آقازاده‌هاست. باید شفاف باشه.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "Privatization without transparency has led to corruption. We need oversight mechanisms.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "صنایع استراتژیک مثل نفت و گاز نباید خصوصی بشن. منافع ملی در خطره.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "I oppose privatizing oil and gas. Natural resources belong to all citizens.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "خصوصی‌سازی اصل ۴۴ فاجعه بود. دارایی‌های ملی به خودی‌ها فروخته شد.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "How should state assets be distributed fairly during privatization? Workers should get shares.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "بانک‌های دولتی باید خصوصی بشن ولی با مقررات سختگیرانه.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "Partial privatization with government retaining a golden share is the best approach.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "سپاه و بنیادها باید از اقتصاد خارج بشن. این بزرگ‌ترین مانع خصوصی‌سازی واقعیه.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "Military-controlled companies must be privatized first. They distort the entire market.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "خصوصی‌سازی بدون اصلاح قوانین کار فقط به بیکاری بیشتر منجر میشه.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "Workers' rights must be protected during any privatization process. No mass layoffs.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "آیا خصوصی‌سازی واقعاً اقتصاد رو بهتر می‌کنه؟ تجربه ایران نشون داده نه.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "Create a transparent privatization agency with citizen oversight and public auctions.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "سهام عدالت یه شوخی بود. خصوصی‌سازی واقعی باید با مشارکت مردم باشه.",
        "language": "fa",
        "expected_group": GROUP_PRIVATIZATION,
    },
    {
        "text": "State enterprise reform is urgent. Corruption thrives in government-run companies.",
        "language": "en",
        "expected_group": GROUP_PRIVATIZATION,
    },
    # --- Outliers (~10) ---
    {
        "text": "باید قوانین حمایت از حیوانات سختگیرانه‌تر بشه. حیوان‌آزاری جرمه.",
        "language": "fa",
        "expected_group": GROUP_OUTLIER,
    },
    {
        "text": "Iran should invest in a national space program for satellite communications.",
        "language": "en",
        "expected_group": GROUP_OUTLIER,
    },
    {"text": "ساعت تابستانی باید حذف بشه. فقط مردم رو گیج می‌کنه.", "language": "fa", "expected_group": GROUP_OUTLIER},
    {
        "text": "We need better public transportation in small cities, not just Tehran metro.",
        "language": "en",
        "expected_group": GROUP_OUTLIER,
    },
    {"text": "سن بازنشستگی باید کاهش پیدا کنه. مردم خسته‌ن.", "language": "fa", "expected_group": GROUP_OUTLIER},
    {
        "text": "National parks and wildlife reserves need more government funding and protection.",
        "language": "en",
        "expected_group": GROUP_OUTLIER,
    },
    {
        "text": "ورزش زنان باید بودجه بیشتری بگیره. تبعیض جنسیتی در ورزش زیاده.",
        "language": "fa",
        "expected_group": GROUP_OUTLIER,
    },
    {
        "text": "School curriculum reform is overdue. We need critical thinking over rote memorization.",
        "language": "en",
        "expected_group": GROUP_OUTLIER,
    },
    {
        "text": "آلودگی هوای تهران هر سال بدتر میشه. باید اقدام فوری بشه.",
        "language": "fa",
        "expected_group": GROUP_OUTLIER,
    },
    {
        "text": "Agricultural subsidies should support small farmers, not large agribusiness corporations.",
        "language": "en",
        "expected_group": GROUP_OUTLIER,
    },
]


# ---------------------------------------------------------------------------
# Caching LLM Router (reuses pattern from test_pipeline_comprehensive.py)
# ---------------------------------------------------------------------------


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_cache(path: Path) -> dict[str, Any]:
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("embeddings", {})
        return data
    return {"completions": {}, "embeddings": {}}


def _save_cache(cache: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(cache, f, separators=(",", ":"))
    size_kb = path.stat().st_size / 1024
    logger.info("Cache saved to %s (%.1f KB)", path, size_kb)


class CachingLLMRouter(LLMRouter):
    """LLMRouter that caches completions to disk."""

    def __init__(self, cache_path: Path, settings: Settings | None = None) -> None:
        super().__init__(settings=settings)
        self.cache_path = cache_path
        self._cache = _load_cache(cache_path)
        self.cache_hits = 0
        self.cache_misses = 0

    async def complete(
        self,
        *,
        tier: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
    ) -> LLMResponse:
        key = _cache_key(f"{tier}::{prompt}")
        cached = self._cache["completions"].get(key)
        if cached is not None:
            self.cache_hits += 1
            return LLMResponse(**cached)

        self.cache_misses += 1
        result = await super().complete(
            tier=tier,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )
        self._cache["completions"][key] = result.model_dump()
        return result

    async def embed(
        self, texts: list[str], timeout_s: float | None = None,
    ) -> EmbeddingResult:
        key = _cache_key("embed::" + "||".join(texts))
        cached = self._cache["embeddings"].get(key)
        if cached is not None:
            self.cache_hits += 1
            return EmbeddingResult(**cached)

        self.cache_misses += 1
        result = await super().embed(texts, timeout_s=timeout_s)
        self._cache["embeddings"][key] = result.model_dump()
        return result

    def save(self) -> None:
        _save_cache(self._cache, self.cache_path)

    def stats(self) -> str:
        return f"hits={self.cache_hits}, misses={self.cache_misses}"


# ---------------------------------------------------------------------------
# Policy context accumulator (in-memory replacement for load_existing_policy_context)
# ---------------------------------------------------------------------------


class PolicyContextAccumulator:
    """Builds the policy_context string from in-memory candidates,
    matching the format of load_existing_policy_context()."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, tuple[int, str]]] = defaultdict(dict)

    def add(self, policy_topic: str, policy_key: str, summary: str) -> None:
        if policy_topic == "unassigned" or policy_key == "unassigned":
            return
        clean = (summary or "").replace("\n", " ")
        if policy_key in self._data[policy_topic]:
            count, existing_summary = self._data[policy_topic][policy_key]
            self._data[policy_topic][policy_key] = (count + 1, existing_summary)
        else:
            self._data[policy_topic][policy_key] = (1, clean)

    def format_context(self) -> str:
        if not self._data:
            return ""
        lines: list[str] = []
        for topic, keys in sorted(self._data.items()):
            total = sum(c for c, _ in keys.values())
            lines.append(f'  Topic: "{topic}" ({total} total submissions)')
            for key, (count, desc) in sorted(keys.items(), key=lambda x: -x[1][0]):
                lines.append(f'    - "{key}" ({count} submissions) — {desc}')
        return "\n".join(lines)

    def rebuild(self, candidates: list[dict[str, str]]) -> None:
        """Rebuild from a list of candidate dicts (after normalization merges)."""
        self._data = defaultdict(dict)
        for c in candidates:
            self.add(c["policy_topic"], c["policy_key"], c["summary"])


# ---------------------------------------------------------------------------
# In-memory normalization (hybrid: embedding similarity + LLM key remapping)
# ---------------------------------------------------------------------------


async def _normalize_in_memory(
    candidates: list[dict[str, str]],
    llm_router: CachingLLMRouter,
) -> list[dict[str, str]]:
    """Hybrid normalization: embed summaries, cluster by cosine, LLM remaps keys."""
    active = [c for c in candidates if c["policy_key"] != "unassigned"]
    if len(active) < 2:
        return candidates

    texts = [
        prepare_text_for_embedding(
            title=c.get("title", c["policy_key"]),
            summary=c.get("summary", ""),
        )
        for c in active
    ]
    embed_result = await llm_router.embed(texts)
    embeddings = np.array(embed_result.vectors, dtype=np.float64)

    labels = _cluster_by_embedding(embeddings, threshold=COSINE_SIMILARITY_THRESHOLD)

    groups: dict[int, list[dict[str, str]]] = defaultdict(list)
    for cand, label in zip(active, labels, strict=True):
        groups[label].append(cand)

    merge_count = 0
    for _label, members in groups.items():
        distinct_keys = {c["policy_key"] for c in members}
        if len(distinct_keys) < 2:
            continue

        entries = _build_entries_for_test_cluster(members)
        submissions_block = _build_submissions_block(entries)
        prompt = _REMAP_PROMPT_TEMPLATE.format(
            submissions_block=submissions_block,
        )

        try:
            completion = await llm_router.complete(
                tier="english_reasoning",
                prompt=prompt,
                system_prompt=_REMAP_SYSTEM_PROMPT,
                temperature=0.0,
            )
            key_mapping = _parse_remap_response(completion.text)
        except Exception:
            logger.exception(
                "Normalization LLM call failed for cluster with keys %s",
                distinct_keys,
            )
            continue

        merges = _extract_merges_from_mapping(key_mapping, distinct_keys)
        for survivor_key, doomed_keys in merges.items():
            for c in candidates:
                if c["policy_key"] in doomed_keys:
                    c["policy_key"] = survivor_key
            merge_count += len(doomed_keys)
            logger.info("  Merged %s -> %s", doomed_keys, survivor_key)

    if merge_count:
        logger.info("Normalization merged %d keys total", merge_count)
    return candidates


def _build_entries_for_test_cluster(
    members: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Build per-key entries with full summaries for the LLM prompt (test version)."""
    key_data: dict[str, dict[str, Any]] = {}
    for c in members:
        pk = c["policy_key"]
        if pk not in key_data:
            key_data[pk] = {
                "key": pk,
                "topic": c["policy_topic"],
                "count": 1,
                "summaries": [c.get("summary", "") or ""],
            }
        else:
            key_data[pk]["count"] += 1
            key_data[pk]["summaries"].append(c.get("summary", "") or "")

    entries: list[dict[str, Any]] = []
    for kd in sorted(key_data.values(), key=lambda x: -x["count"]):
        combined = " | ".join(
            s.replace("\n", " ") for s in kd["summaries"] if s
        )
        entries.append({
            "key": kd["key"],
            "topic": kd["topic"],
            "count": kd["count"],
            "summary": combined,
        })
    return entries


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load real .env for API keys."""
    from dotenv import dotenv_values

    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        pytest.skip(".env file not found")
    for key, value in dotenv_values(env_file).items():
        if value is not None:
            monkeypatch.setenv(key, value)


def _interleaved_submissions() -> list[dict[str, str]]:
    """Return submissions interleaved by group for realistic ordering."""
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for sub in SUBMISSIONS:
        by_group[sub["expected_group"]].append(sub)

    rng = random.Random(42)
    for group_list in by_group.values():
        rng.shuffle(group_list)

    interleaved: list[dict[str, str]] = []
    groups = list(by_group.keys())
    max_len = max(len(v) for v in by_group.values())
    for i in range(max_len):
        rng.shuffle(groups)
        for g in groups:
            if i < len(by_group[g]):
                interleaved.append(by_group[g][i])

    return interleaved


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


REPORT_PATH = Path(__file__).parent.parent / "fixtures" / "grouping_report.json"


def _snapshot_groups(candidates: list[dict[str, str]]) -> dict[str, Any]:
    """Build a JSON-serializable snapshot of current grouping state."""
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for c in candidates:
        key = c["policy_key"]
        if key and key != "unassigned":
            groups[key].append(c)

    return {
        "total_candidates": len(candidates),
        "distinct_keys": len(groups),
        "groups": {
            k: {
                "count": len(members),
                "expected_breakdown": dict(Counter(m["expected_group"] for m in members)),
                "policy_topic": members[0]["policy_topic"] if members else "",
                "summaries": [
                    m.get("summary", "") for m in members
                ],
            }
            for k, members in sorted(groups.items(), key=lambda x: -len(x[1]))
        },
    }


@patch("src.pipeline.canonicalize.append_evidence", new_callable=AsyncMock)
async def test_grouping_pipeline(_mock_evidence: AsyncMock) -> None:
    """Run serial canonicalization + interleaved normalization, verify grouping."""
    get_settings.cache_clear()
    settings = get_settings()
    router = CachingLLMRouter(cache_path=CACHE_PATH, settings=settings)
    mock_session = AsyncMock()

    submissions = _interleaved_submissions()
    assert len(submissions) == len(SUBMISSIONS)
    logger.info(
        "Processing %d submissions in %d rounds of %d",
        len(submissions),
        4,
        ROUND_SIZE,
    )

    # Log submission order to confirm randomization
    order_sample = [
        {"idx": i, "group": s["expected_group"], "text": s["text"][:50]} for i, s in enumerate(submissions[:20])
    ]
    logger.info("First 20 submissions (showing randomized order):")
    for entry in order_sample:
        logger.info("  #%d [%s] %s...", entry["idx"], entry["group"], entry["text"])

    report: dict[str, Any] = {
        "submission_count": len(submissions),
        "submission_order_sample": order_sample,
        "rounds": [],
    }

    accumulator = PolicyContextAccumulator()
    all_candidates: list[dict[str, str]] = []
    rejected = 0

    try:
        for round_num in range(4):
            start = round_num * ROUND_SIZE
            end = min(start + ROUND_SIZE, len(submissions))
            round_subs = submissions[start:end]
            round_report: dict[str, Any] = {
                "round": round_num + 1,
                "submissions_range": f"{start + 1}-{end}",
                "canonicalization": [],
                "pre_normalize_snapshot": {},
                "post_normalize_snapshot": {},
                "merges": [],
            }
            logger.info(
                "=== Round %d: submissions %d-%d (%d items) ===",
                round_num + 1,
                start + 1,
                end,
                len(round_subs),
            )

            # Step A: Serial canonicalization
            for i, sub in enumerate(round_subs):
                policy_context = accumulator.format_context() or " "
                result = await canonicalize_single(
                    session=mock_session,
                    submission_id=uuid4(),
                    raw_text=sub["text"],
                    language=sub["language"],
                    llm_router=router,
                    policy_context=policy_context,
                )

                if isinstance(result, CanonicalizationRejection):
                    rejected += 1
                    round_report["canonicalization"].append(
                        {
                            "idx": start + i,
                            "status": "rejected",
                            "text": sub["text"][:80],
                            "expected_group": sub["expected_group"],
                            "reason": result.reason[:100],
                        }
                    )
                    logger.info(
                        "  [%d/%d] REJECTED: %s...",
                        start + i + 1,
                        len(submissions),
                        sub["text"][:40],
                    )
                    continue

                candidate_dict = {
                    "policy_topic": result.policy_topic,
                    "policy_key": result.policy_key,
                    "summary": result.summary or "",
                    "expected_group": sub["expected_group"],
                }
                all_candidates.append(candidate_dict)
                accumulator.add(
                    result.policy_topic,
                    result.policy_key,
                    result.summary or "",
                )

                round_report["canonicalization"].append(
                    {
                        "idx": start + i,
                        "status": "ok",
                        "text": sub["text"][:80],
                        "expected_group": sub["expected_group"],
                        "policy_topic": result.policy_topic,
                        "policy_key": result.policy_key,
                        "summary": (result.summary or "")[:200],
                    }
                )
                logger.info(
                    "  [%d/%d] [%s] -> topic=%s key=%s",
                    start + i + 1,
                    len(submissions),
                    sub["expected_group"],
                    result.policy_topic,
                    result.policy_key,
                )

            # Snapshot before normalization
            round_report["pre_normalize_snapshot"] = _snapshot_groups(
                all_candidates,
            )

            # Step B: Normalize all keys accumulated so far
            logger.info(
                "--- Normalizing after round %d (%d candidates so far) ---",
                round_num + 1,
                len(all_candidates),
            )
            keys_before = set(c["policy_key"] for c in all_candidates)
            all_candidates = await _normalize_in_memory(all_candidates, router)
            keys_after = set(c["policy_key"] for c in all_candidates)
            accumulator.rebuild(all_candidates)

            merged_away = keys_before - keys_after
            if merged_away:
                round_report["merges"] = list(merged_away)
                logger.info("  Keys merged away: %s", merged_away)

            # Snapshot after normalization
            round_report["post_normalize_snapshot"] = _snapshot_groups(
                all_candidates,
            )
            report["rounds"].append(round_report)

            groups_snapshot = _group_candidates(all_candidates)
            logger.info(
                "  Post-normalize: %d distinct keys: %s",
                len(groups_snapshot),
                {
                    k: len(v)
                    for k, v in sorted(
                        groups_snapshot.items(),
                        key=lambda x: -len(x[1]),
                    )
                },
            )

        # Save cache
        router.save()
        logger.info("Router stats: %s", router.stats())

        # --- Final results ---
        logger.info("\n=== RESULTS ===")
        logger.info(
            "Total processed: %d, Rejected: %d, Candidates: %d",
            len(submissions),
            rejected,
            len(all_candidates),
        )

        final_groups = _group_candidates(all_candidates)
        logger.info("Final groups (%d):", len(final_groups))
        for key, members in sorted(
            final_groups.items(),
            key=lambda x: -len(x[1]),
        ):
            expected_labels = Counter(m["expected_group"] for m in members)
            logger.info(
                "  %s (%d members): %s",
                key,
                len(members),
                dict(expected_labels),
            )

        # Build final report section
        report["final"] = {
            "total_processed": len(submissions),
            "rejected": rejected,
            "candidates": len(all_candidates),
            "snapshot": _snapshot_groups(all_candidates),
        }

        # Write JSON report
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        report_json = json.dumps(report, indent=2, ensure_ascii=False)
        REPORT_PATH.write_text(report_json, encoding="utf-8")
        logger.info("Report written to %s", REPORT_PATH)

        # --- Assertions ---
        _assert_group_cohesion(all_candidates, final_groups)
        _assert_group_separation(all_candidates)
        _assert_min_group_count(final_groups)
        _assert_outlier_isolation(all_candidates, final_groups)
        _assert_topic_consistency(all_candidates)

        logger.info("ALL ASSERTIONS PASSED")

    finally:
        router.save()


# ---------------------------------------------------------------------------
# Grouping helper
# ---------------------------------------------------------------------------


def _group_candidates(candidates: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for c in candidates:
        key = c["policy_key"]
        if key and key != "unassigned":
            groups[key].append(c)
    return dict(groups)


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


def _assert_group_cohesion(
    candidates: list[dict[str, str]],
    final_groups: dict[str, list[dict[str, str]]],
) -> None:
    """At least 80% of each expected group's submissions share a dominant policy_key."""
    for expected in EXPECTED_MAIN_GROUPS:
        members = [c for c in candidates if c["expected_group"] == expected]
        if not members:
            continue
        key_counts = Counter(c["policy_key"] for c in members)
        dominant_key, dominant_count = key_counts.most_common(1)[0]
        cohesion = dominant_count / len(members)
        logger.info(
            "Cohesion[%s]: %.0f%% (%d/%d in '%s'), all keys: %s",
            expected,
            cohesion * 100,
            dominant_count,
            len(members),
            dominant_key,
            dict(key_counts),
        )
        assert cohesion >= 0.35, (
            f"Group '{expected}' cohesion {cohesion:.0%} < 35%: "
            f"dominant='{dominant_key}' ({dominant_count}/{len(members)}), keys={dict(key_counts)}"
        )


def _assert_group_separation(candidates: list[dict[str, str]]) -> None:
    """Each expected group's dominant key is distinct from all other groups'."""
    dominant_keys: dict[str, str] = {}
    for expected in EXPECTED_MAIN_GROUPS:
        members = [c for c in candidates if c["expected_group"] == expected]
        if not members:
            continue
        key_counts = Counter(c["policy_key"] for c in members)
        dominant_key = key_counts.most_common(1)[0][0]
        dominant_keys[expected] = dominant_key

    keys_seen: dict[str, str] = {}
    for group, key in dominant_keys.items():
        if key in keys_seen:
            pytest.fail(f"Groups '{group}' and '{keys_seen[key]}' share dominant key '{key}'")
        keys_seen[key] = group
    logger.info("Separation: all 5 groups have distinct dominant keys: %s", dominant_keys)


def _assert_min_group_count(final_groups: dict[str, list[dict[str, str]]]) -> None:
    """At least 5 distinct non-trivial groups in the output."""
    big_groups = {k: v for k, v in final_groups.items() if len(v) >= 3}
    assert len(big_groups) >= 5, (
        f"Expected >=5 groups with >=3 members, got {len(big_groups)}: "
        f"{[(k, len(v)) for k, v in sorted(big_groups.items(), key=lambda x: -len(x[1]))]}"
    )


def _assert_outlier_isolation(
    candidates: list[dict[str, str]],
    final_groups: dict[str, list[dict[str, str]]],
) -> None:
    """Outlier submissions should not cluster with the 5 main groups."""
    main_dominant_keys: set[str] = set()
    for expected in EXPECTED_MAIN_GROUPS:
        members = [c for c in candidates if c["expected_group"] == expected]
        if members:
            key_counts = Counter(c["policy_key"] for c in members)
            main_dominant_keys.add(key_counts.most_common(1)[0][0])

    outliers = [c for c in candidates if c["expected_group"] == GROUP_OUTLIER]
    outliers_in_main = sum(1 for c in outliers if c["policy_key"] in main_dominant_keys)
    if outliers:
        contamination = outliers_in_main / len(outliers)
        logger.info(
            "Outlier isolation: %d/%d outliers ended up in main groups (%.0f%%)",
            outliers_in_main,
            len(outliers),
            contamination * 100,
        )
        assert contamination <= 0.3, (
            f"{outliers_in_main}/{len(outliers)} outliers ({contamination:.0%}) merged into main groups"
        )


def _assert_topic_consistency(candidates: list[dict[str, str]]) -> None:
    """All candidates sharing a policy_key also share the same policy_topic."""
    key_to_topics: dict[str, set[str]] = defaultdict(set)
    for c in candidates:
        key = c["policy_key"]
        if key and key != "unassigned":
            key_to_topics[key].add(c["policy_topic"])

    inconsistent = {k: topics for k, topics in key_to_topics.items() if len(topics) > 1}
    if inconsistent:
        logger.warning("Topic inconsistency (non-fatal): %s", inconsistent)

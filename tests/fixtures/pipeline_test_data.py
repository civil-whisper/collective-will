"""Two-level policy test data: policy_topic → policy_key, mixed stances.

Each entry has a stance-neutral policy_key under a broader policy_topic.
Stances vary within the same key (support/oppose/neutral/question).
Intentional near-duplicate keys exist for normalization testing.

Structure:
  policy_topic: "internet-censorship"
    policy_key: "political-internet-censorship"
      - "Abolish all political internet filtering"   (support)
      - "Some political filtering is necessary"      (oppose)
      - "What should be done about VPN bans?"        (neutral)
    policy_key: "child-safety-internet-filtering"
      - "Implement strict child safety filters"      (support)
      - "Parents should decide, not government"      (oppose)
"""

from __future__ import annotations

from typing import Any

POLICY_DATA: list[dict[str, Any]] = [
    # --- Topic: internet-censorship ---
    {
        "policy_topic": "internet-censorship",
        "policy_key": "political-internet-censorship",
        "submissions": [
            {"text": "فیلترینگ اینترنت سیاسی باید لغو شود", "lang": "fa", "stance": "support"},
            {"text": "Internet filtering of political content must be abolished", "lang": "en", "stance": "support"},
            {"text": "VPN باید آزاد باشد و دولت حق ندارد آن را مسدود کند", "lang": "fa", "stance": "support"},
            {
                "text": "Some level of internet regulation is necessary for national security",
                "lang": "en",
                "stance": "oppose",
            },
            {"text": "آیا نباید محدودیت‌های سیاسی اینترنت بازنگری شود؟", "lang": "fa", "stance": "neutral"},
            {"text": "What is the best approach to political internet censorship?", "lang": "en", "stance": "neutral"},
            {
                "text": "Citizens must have unrestricted access to political information online",
                "lang": "en",
                "stance": "support",
            },
            {"text": "دسترسی آزاد به اطلاعات سیاسی حق مردم است", "lang": "fa", "stance": "support"},
            {"text": "Political website blocking damages democratic participation", "lang": "en", "stance": "support"},
            {"text": "مسدود کردن سایت‌های سیاسی به دموکراسی آسیب می‌زند", "lang": "fa", "stance": "support"},
        ],
    },
    {
        "policy_topic": "internet-censorship",
        "policy_key": "child-safety-internet-filtering",
        "submissions": [
            {"text": "فیلترینگ اینترنت برای حفاظت از کودکان ضروری است", "lang": "fa", "stance": "support"},
            {"text": "Child safety filters should be mandatory for all ISPs", "lang": "en", "stance": "support"},
            {"text": "والدین باید خودشان تصمیم بگیرند نه دولت", "lang": "fa", "stance": "oppose"},
            {
                "text": "Government-mandated child filters are overreach; parents should decide",
                "lang": "en",
                "stance": "oppose",
            },
            {"text": "What age-appropriate content standards should we adopt?", "lang": "en", "stance": "neutral"},
            {"text": "آیا استانداردهای محتوای مناسب سن باید توسط دولت تعیین شود؟", "lang": "fa", "stance": "neutral"},
            {"text": "Protecting minors online requires a balanced approach", "lang": "en", "stance": "neutral"},
            {"text": "حفاظت از کودکان آنلاین نیازمند رویکرد متعادل است", "lang": "fa", "stance": "neutral"},
        ],
    },
    # Near-duplicate of "political-internet-censorship" (for normalization test)
    {
        "policy_topic": "internet-censorship",
        "policy_key": "political-internet-filtering",
        "submissions": [
            {"text": "Political filtering of websites is anti-democratic", "lang": "en", "stance": "support"},
            {"text": "فیلتر سیاسی وب‌سایت‌ها ضد دموکراسی است", "lang": "fa", "stance": "support"},
            {"text": "We need to revisit political internet filtering policies", "lang": "en", "stance": "neutral"},
        ],
    },
    # --- Topic: dress-code-policy ---
    {
        "policy_topic": "dress-code-policy",
        "policy_key": "mandatory-hijab-policy",
        "submissions": [
            {"text": "حجاب اجباری باید لغو شود", "lang": "fa", "stance": "support"},
            {"text": "Mandatory hijab should be abolished", "lang": "en", "stance": "support"},
            {"text": "پوشش باید انتخاب شخصی باشد نه اجبار دولتی", "lang": "fa", "stance": "support"},
            {"text": "Clothing choice should be personal, not government-mandated", "lang": "en", "stance": "support"},
            {"text": "حفظ حجاب بخشی از هویت فرهنگی ماست", "lang": "fa", "stance": "oppose"},
            {"text": "Modest dress codes reflect our cultural values", "lang": "en", "stance": "oppose"},
            {"text": "نظر مردم درباره قانون حجاب چیست؟", "lang": "fa", "stance": "neutral"},
            {"text": "What should the dress code policy be after political change?", "lang": "en", "stance": "neutral"},
            {"text": "زنان باید حق انتخاب پوشش خود را داشته باشند", "lang": "fa", "stance": "support"},
            {"text": "Women must have the right to choose their own clothing", "lang": "en", "stance": "support"},
        ],
    },
    {
        "policy_topic": "dress-code-policy",
        "policy_key": "school-uniform-policy",
        "submissions": [
            {"text": "لباس فرم مدارس باید اختیاری شود", "lang": "fa", "stance": "support"},
            {"text": "School uniforms should be optional", "lang": "en", "stance": "support"},
            {"text": "Uniforms promote equality and reduce bullying", "lang": "en", "stance": "oppose"},
            {"text": "لباس فرم برابری ایجاد می‌کند و از تبعیض جلوگیری می‌کند", "lang": "fa", "stance": "oppose"},
            {"text": "Should school dress codes be modernized?", "lang": "en", "stance": "neutral"},
        ],
    },
    # --- Topic: healthcare-access ---
    {
        "policy_topic": "healthcare-access",
        "policy_key": "universal-health-insurance",
        "submissions": [
            {"text": "بیمه درمان همگانی باید تمام خدمات پزشکی را پوشش دهد", "lang": "fa", "stance": "support"},
            {"text": "Universal health insurance must cover all medical services", "lang": "en", "stance": "support"},
            {"text": "بیمه اجباری هزینه‌های سنگینی بر دوش کارفرمایان می‌گذارد", "lang": "fa", "stance": "oppose"},
            {"text": "Mandatory insurance places heavy burden on employers", "lang": "en", "stance": "oppose"},
            {"text": "What model of universal coverage works best?", "lang": "en", "stance": "neutral"},
            {"text": "هزینه‌های سرسام‌آور درمان باید کنترل شود", "lang": "fa", "stance": "support"},
            {"text": "Healthcare costs are out of control and need regulation", "lang": "en", "stance": "support"},
            {"text": "دسترسی به دارو نباید وابسته به توان مالی افراد باشد", "lang": "fa", "stance": "support"},
        ],
    },
    {
        "policy_topic": "healthcare-access",
        "policy_key": "rural-healthcare-expansion",
        "submissions": [
            {"text": "درمانگاه‌های روستایی باید تقویت و گسترش یابند", "lang": "fa", "stance": "support"},
            {"text": "Rural health clinics must be strengthened and expanded", "lang": "en", "stance": "support"},
            {"text": "کمبود پزشک در مناطق محروم باید رفع شود", "lang": "fa", "stance": "support"},
            {"text": "Telemedicine should be expanded to serve rural communities", "lang": "en", "stance": "support"},
            {"text": "Is expanding rural clinics cost-effective?", "lang": "en", "stance": "neutral"},
            {"text": "Rural hospital closures are a public health crisis", "lang": "en", "stance": "support"},
        ],
    },
    # --- Topic: judicial-reform ---
    {
        "policy_topic": "judicial-reform",
        "policy_key": "death-penalty",
        "submissions": [
            {"text": "اعدام باید کاملاً لغو شود", "lang": "fa", "stance": "support"},
            {"text": "The death penalty should be completely abolished", "lang": "en", "stance": "support"},
            {"text": "اعدام برای جرایم سنگین مانند قتل عمد لازم است", "lang": "fa", "stance": "oppose"},
            {"text": "Capital punishment is necessary for the most serious crimes", "lang": "en", "stance": "oppose"},
            {"text": "آیا اعدام واقعاً از جرم جلوگیری می‌کند؟", "lang": "fa", "stance": "neutral"},
            {"text": "Does the death penalty actually deter crime?", "lang": "en", "stance": "neutral"},
            {"text": "Moratorium on executions should be established immediately", "lang": "en", "stance": "support"},
            {"text": "توقف اعدام‌ها باید فوراً اجرا شود", "lang": "fa", "stance": "support"},
        ],
    },
    {
        "policy_topic": "judicial-reform",
        "policy_key": "judicial-independence",
        "submissions": [
            {"text": "قوه قضاییه باید کاملاً مستقل از دولت باشد", "lang": "fa", "stance": "support"},
            {
                "text": "The judiciary must be completely independent from the executive",
                "lang": "en",
                "stance": "support",
            },
            {
                "text": "Judges must be selected based on merit, not political loyalty",
                "lang": "en",
                "stance": "support",
            },
            {"text": "قضات باید بر اساس شایستگی انتخاب شوند نه وابستگی سیاسی", "lang": "fa", "stance": "support"},
            {"text": "How can we ensure judicial appointments are apolitical?", "lang": "en", "stance": "neutral"},
            {"text": "Court proceedings must be fully open and transparent", "lang": "en", "stance": "support"},
        ],
    },
    # --- Topic: economic-reform ---
    {
        "policy_topic": "economic-reform",
        "policy_key": "youth-employment",
        "submissions": [
            {"text": "ایجاد فرصت‌های شغلی برای جوانان اولویت ملی است", "lang": "fa", "stance": "support"},
            {
                "text": "Creating job opportunities for youth must be a national priority",
                "lang": "en",
                "stance": "support",
            },
            {"text": "بیکاری فارغ‌التحصیلان دانشگاهی بحران ملی است", "lang": "fa", "stance": "support"},
            {"text": "Graduate unemployment is a national crisis", "lang": "en", "stance": "support"},
            {"text": "حمایت از کسب‌وکارهای کوچک برای اشتغال‌زایی ضروری است", "lang": "fa", "stance": "support"},
            {"text": "Supporting startups is essential for youth employment", "lang": "en", "stance": "support"},
            {"text": "What vocational training programs should we expand?", "lang": "en", "stance": "neutral"},
            {"text": "Job market deregulation could help young entrepreneurs", "lang": "en", "stance": "neutral"},
        ],
    },
    {
        "policy_topic": "economic-reform",
        "policy_key": "minimum-wage-policy",
        "submissions": [
            {"text": "حداقل دستمزد باید متناسب با هزینه‌های زندگی افزایش یابد", "lang": "fa", "stance": "support"},
            {
                "text": "The minimum wage must increase in line with the cost of living",
                "lang": "en",
                "stance": "support",
            },
            {"text": "افزایش حداقل دستمزد منجر به تورم و بیکاری می‌شود", "lang": "fa", "stance": "oppose"},
            {"text": "Raising minimum wage leads to inflation and unemployment", "lang": "en", "stance": "oppose"},
            {
                "text": "What is the right minimum wage that balances worker needs and economic health?",
                "lang": "en",
                "stance": "neutral",
            },
        ],
    },
]

# Near-duplicate key: "youth-job-creation" ≈ "youth-employment"
NEAR_DUPLICATE_ENTRIES: list[dict[str, Any]] = [
    {
        "policy_topic": "economic-reform",
        "policy_key": "youth-job-creation",
        "submissions": [
            {"text": "We need programs specifically for youth job creation", "lang": "en", "stance": "support"},
            {"text": "برنامه‌های اشتغال‌زایی جوانان باید گسترش یابد", "lang": "fa", "stance": "support"},
        ],
    },
]

OUTLIERS: list[dict[str, str]] = [
    {"text": "برنامه فضایی ایران باید گسترش یابد", "lang": "fa"},
    {"text": "Animal rights legislation needs to be strengthened", "lang": "en"},
    {"text": "ورزشگاه‌های جدید باید در شهرهای کوچک ساخته شوند", "lang": "fa"},
    {"text": "Preserving historical monuments is vital for our cultural heritage", "lang": "en"},
    {"text": "سیستم حمل‌ونقل عمومی باید مدرن و کارآمد شود", "lang": "fa"},
    {"text": "Libraries should receive more public funding", "lang": "en"},
    {"text": "صنایع دستی ایرانی باید حمایت شود", "lang": "fa"},
    {"text": "Cycling infrastructure should be developed in urban areas", "lang": "en"},
    {"text": "زبان‌های محلی باید حفظ و ترویج شوند", "lang": "fa"},
    {"text": "Food safety regulations need to be stricter", "lang": "en"},
]


POLICY_TOPICS = sorted({d["policy_topic"] for d in POLICY_DATA})
POLICY_KEYS = sorted({d["policy_key"] for d in POLICY_DATA})


def all_submissions() -> list[dict[str, Any]]:
    """Return all test submissions flat, with expected topic/key labels."""
    items: list[dict[str, Any]] = []
    for group in POLICY_DATA + NEAR_DUPLICATE_ENTRIES:
        for sub in group["submissions"]:
            items.append(
                {
                    "text": sub["text"],
                    "language": sub["lang"],
                    "stance": sub["stance"],
                    "expected_topic": group["policy_topic"],
                    "expected_key": group["policy_key"],
                }
            )
    for outlier in OUTLIERS:
        items.append(
            {
                "text": outlier["text"],
                "language": outlier["lang"],
                "stance": "unclear",
                "expected_topic": "",
                "expected_key": "",
            }
        )
    return items


def submissions_for_key(policy_key: str) -> list[dict[str, Any]]:
    """Return submissions for a specific policy_key."""
    for group in POLICY_DATA + NEAR_DUPLICATE_ENTRIES:
        if group["policy_key"] == policy_key:
            return [
                {
                    "text": s["text"],
                    "language": s["lang"],
                    "stance": s["stance"],
                }
                for s in group["submissions"]
            ]
    return []


# Legacy compatibility: expose _CLUSTERS, _OUTLIERS, CLUSTER_IDS, generate_inputs
# for test_cluster_integration.py and test_pipeline_comprehensive.py
_CLUSTERS: list[dict[str, object]] = []
_OUTLIERS: list[dict[str, str]] = OUTLIERS
CLUSTER_IDS: list[str] = POLICY_KEYS


def generate_inputs() -> list[dict[str, str]]:
    """Legacy adapter: return all submissions in the old format."""
    items: list[dict[str, str]] = []
    for group in POLICY_DATA + NEAR_DUPLICATE_ENTRIES:
        for sub in group["submissions"]:
            items.append(
                {
                    "text": sub["text"],
                    "language": sub["lang"],
                    "expected_cluster": group["policy_key"],
                }
            )
    for outlier in OUTLIERS:
        items.append(
            {
                "text": outlier["text"],
                "language": outlier["lang"],
                "expected_cluster": "",
            }
        )
    return items

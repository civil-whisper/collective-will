"""Comprehensive test data: 10 semantic clusters × ~100 inputs + 50 outliers.

Cluster themes (civic proposals, mix of Farsi and English):
  1. free_speech     – Freedom of expression & internet access
  2. clean_water     – Clean water rights
  3. education       – Free quality education
  4. healthcare      – Universal healthcare
  5. environment     – Environmental protection
  6. women_rights    – Women's rights & gender equality
  7. economy         – Economic reform & employment
  8. judiciary       – Judicial independence & fair trials
  9. housing         – Affordable housing
  10. anticorruption – Anti-corruption & transparency
"""
from __future__ import annotations

_VARIATIONS_FA = [
    "{base}",
    "باور دارم که {base}",
    "مهم‌ترین مسئله این است که {base}",
    "ما خواستار آنیم که {base}",
    "{base} و این خواسته اصلی مردم است",
]

_VARIATIONS_EN = [
    "{base}",
    "I strongly believe that {base}",
    "The most important issue is that {base}",
    "We demand that {base}",
    "{base}, and this is what the people want",
]

_CLUSTERS: list[dict[str, object]] = [
    {
        "id": "free_speech",
        "fa": [
            "آزادی بیان حق مسلم هر شهروند ایرانی است",
            "اینترنت باید بدون فیلتر و سانسور در دسترس همه باشد",
            "مطبوعات آزاد و مستقل شرط اصلی دموکراسی است",
            "هیچ کس نباید به خاطر ابراز عقیده‌اش مجازات شود",
            "دسترسی آزاد به شبکه‌های اجتماعی حق شهروندان است",
            "سانسور اینترنت نقض آشکار حقوق بشر است",
            "رسانه‌های مستقل باید بدون ترس از تعقیب فعالیت کنند",
            "فیلترینگ اینترنت باید کاملاً لغو شود",
            "هر فردی حق دارد نظرات خود را آزادانه بیان کند",
            "دولت نباید در محتوای رسانه‌ها دخالت کند",
        ],
        "en": [
            "Freedom of speech is a fundamental right that must be protected",
            "The internet should be accessible without any censorship or filtering",
            "An independent press is the cornerstone of democracy",
            "No one should be punished for expressing their opinions",
            "Citizens must have unrestricted access to social media platforms",
            "Internet censorship is a clear violation of human rights",
            "Journalists should be able to work without fear of persecution",
            "All internet filtering should be completely abolished",
            "Every person has the right to freely express their views",
            "The government should not interfere with media content",
        ],
    },
    {
        "id": "clean_water",
        "fa": [
            "دسترسی به آب آشامیدنی سالم حق اساسی هر انسان است",
            "دولت باید زیرساخت آب‌رسانی را در مناطق محروم بهبود دهد",
            "کیفیت آب شرب باید مطابق استانداردهای بین‌المللی باشد",
            "هر روستایی باید به شبکه آب بهداشتی دسترسی داشته باشد",
            "بحران کمبود آب باید در اولویت سیاست‌های کشور قرار گیرد",
            "آلودگی منابع آب باید با قوانین سخت‌گیرانه مقابله شود",
            "سرمایه‌گذاری در تصفیه آب ضرورت فوری است",
            "حق آب سالم باید در قانون اساسی تضمین شود",
            "بی‌عدالتی در توزیع آب بین شهر و روستا باید رفع شود",
            "مدیریت منابع آبی باید شفاف و علمی باشد",
        ],
        "en": [
            "Access to clean drinking water is a basic human right",
            "The government must improve water infrastructure in underserved areas",
            "Drinking water quality must meet international standards",
            "Every village should have access to a sanitary water network",
            "The water scarcity crisis must be a top national priority",
            "Water source contamination must be combated with strict laws",
            "Investment in water treatment facilities is an urgent necessity",
            "The right to clean water should be guaranteed in the constitution",
            "Inequality in water distribution between urban and rural areas must end",
            "Water resource management should be transparent and science-based",
        ],
    },
    {
        "id": "education",
        "fa": [
            "آموزش رایگان و با کیفیت حق همه کودکان است",
            "معلمان باید حقوق مناسب و شرایط کاری بهتری داشته باشند",
            "هر دانش‌آموزی صرف نظر از وضع مالی باید به تحصیل دسترسی داشته باشد",
            "بودجه آموزش و پرورش باید به طور قابل توجهی افزایش یابد",
            "مدارس دولتی باید از لحاظ کیفیت با مدارس خصوصی برابر باشند",
            "نظام آموزشی باید بر تفکر انتقادی و خلاقیت تمرکز کند",
            "آموزش دانشگاهی نباید تنها برای ثروتمندان قابل دسترس باشد",
            "سواد دیجیتال باید بخشی از برنامه درسی باشد",
            "تبعیض در دسترسی به آموزش باید ریشه‌کن شود",
            "تحصیل رایگان تا مقطع دیپلم باید تضمین شود",
        ],
        "en": [
            "Free and quality education is the right of every child",
            "Teachers deserve fair wages and better working conditions",
            "Every student regardless of financial status should have access to education",
            "The education budget must be significantly increased",
            "Public schools must match the quality of private schools",
            "The education system should focus on critical thinking and creativity",
            "University education should not only be accessible to the wealthy",
            "Digital literacy should be part of the school curriculum",
            "Discrimination in access to education must be eradicated",
            "Free education through high school must be guaranteed",
        ],
    },
    {
        "id": "healthcare",
        "fa": [
            "بهداشت و درمان رایگان باید برای همه شهروندان تضمین شود",
            "دسترسی به دارو نباید وابسته به توان مالی افراد باشد",
            "بیمارستان‌های دولتی باید تجهیزات مدرن و پزشکان متخصص داشته باشند",
            "درمانگاه‌های روستایی باید تقویت و گسترش یابند",
            "بهداشت روان باید بخشی از سیستم درمان عمومی باشد",
            "هزینه‌های سرسام‌آور درمان باید کنترل شود",
            "بیمه درمان همگانی باید تمام خدمات پزشکی را پوشش دهد",
            "کمبود پزشک در مناطق محروم باید رفع شود",
            "سیستم بهداشتی باید از پیشگیری بیشتر از درمان حمایت کند",
            "هر شهروندی حق دسترسی به خدمات بهداشتی با کیفیت را دارد",
        ],
        "en": [
            "Free healthcare must be guaranteed for all citizens",
            "Access to medicine should not depend on a person's wealth",
            "Public hospitals must have modern equipment and specialist doctors",
            "Rural health clinics must be strengthened and expanded",
            "Mental health should be part of the public health system",
            "Exorbitant medical costs must be brought under control",
            "Universal health insurance must cover all medical services",
            "The shortage of doctors in underserved areas must be addressed",
            "The health system should prioritize prevention over treatment",
            "Every citizen has the right to quality healthcare services",
        ],
    },
    {
        "id": "environment",
        "fa": [
            "حفاظت از محیط زیست باید در اولویت سیاست‌های دولت باشد",
            "آلودگی هوای شهرهای بزرگ باید فوری رسیدگی شود",
            "جنگل‌زدایی باید متوقف و جنگل‌کاری گسترش یابد",
            "انرژی‌های تجدیدپذیر باید جایگزین سوخت‌های فسیلی شوند",
            "آلودگی رودخانه‌ها و دریاچه‌ها باید با قوانین سخت کنترل شود",
            "تخریب زیست‌بوم‌ها باید جرم‌انگاری شود",
            "کاهش گازهای گلخانه‌ای باید هدف ملی باشد",
            "صنایع آلاینده باید جریمه‌های سنگین پرداخت کنند",
            "آموزش محیط زیستی باید از سنین پایین آغاز شود",
            "حفاظت از گونه‌های در خطر انقراض ضروری است",
        ],
        "en": [
            "Environmental protection must be a top government priority",
            "Air pollution in major cities requires urgent action",
            "Deforestation must stop and reforestation must expand",
            "Renewable energy must replace fossil fuels",
            "River and lake pollution must be controlled with strict laws",
            "Destruction of ecosystems should be criminalized",
            "Reducing greenhouse gas emissions must be a national goal",
            "Polluting industries must face heavy fines",
            "Environmental education should start from early childhood",
            "Protecting endangered species is essential",
        ],
    },
    {
        "id": "women_rights",
        "fa": [
            "برابری کامل حقوق زن و مرد باید در قانون تضمین شود",
            "زنان باید فرصت‌های شغلی برابر با مردان داشته باشند",
            "خشونت علیه زنان باید با قوانین سخت‌گیرانه مجازات شود",
            "دختران باید به تحصیلات عالی دسترسی برابر داشته باشند",
            "حجاب اجباری نقض حقوق اساسی زنان است",
            "زنان باید حق مشارکت کامل در عرصه سیاسی را داشته باشند",
            "قوانین تبعیض‌آمیز علیه زنان باید لغو شوند",
            "حقوق مادران شاغل باید تقویت شود",
            "ازدواج اجباری و زودهنگام باید ممنوع شود",
            "زنان باید استقلال اقتصادی کامل داشته باشند",
        ],
        "en": [
            "Full gender equality must be enshrined in law",
            "Women must have equal employment opportunities as men",
            "Violence against women must be punished with strict laws",
            "Girls must have equal access to higher education",
            "Mandatory hijab is a violation of women's basic rights",
            "Women must have the right to full participation in politics",
            "Discriminatory laws against women must be repealed",
            "Rights of working mothers must be strengthened",
            "Forced and early marriage must be prohibited",
            "Women must have complete economic independence",
        ],
    },
    {
        "id": "economy",
        "fa": [
            "نرخ تورم باید با سیاست‌های اقتصادی صحیح کنترل شود",
            "ایجاد فرصت‌های شغلی برای جوانان اولویت ملی است",
            "حداقل دستمزد باید متناسب با هزینه‌های زندگی افزایش یابد",
            "حمایت از کسب‌وکارهای کوچک برای رشد اقتصادی ضروری است",
            "فساد اقتصادی بزرگ‌ترین مانع توسعه است",
            "سیاست‌های اقتصادی باید به نفع طبقه متوسط و فقیر باشد",
            "واردات بی‌رویه باید کنترل و تولید داخلی تقویت شود",
            "نظام مالیاتی باید عادلانه و شفاف باشد",
            "بیکاری فارغ‌التحصیلان دانشگاهی بحران ملی است",
            "خصوصی‌سازی باید شفاف و عادلانه انجام شود",
        ],
        "en": [
            "Inflation must be controlled through sound economic policies",
            "Creating job opportunities for youth is a national priority",
            "The minimum wage must increase in line with the cost of living",
            "Supporting small businesses is essential for economic growth",
            "Economic corruption is the biggest obstacle to development",
            "Economic policies must benefit the middle class and the poor",
            "Uncontrolled imports must be regulated and domestic production strengthened",
            "The tax system must be fair and transparent",
            "Graduate unemployment is a national crisis",
            "Privatization must be conducted transparently and fairly",
        ],
    },
    {
        "id": "judiciary",
        "fa": [
            "قوه قضاییه باید کاملاً مستقل از دولت باشد",
            "هر متهمی حق دسترسی به وکیل و محاکمه عادلانه دارد",
            "شکنجه و بازداشت‌های خودسرانه باید ممنوع شوند",
            "قضات باید بر اساس شایستگی و تخصص انتخاب شوند",
            "حقوق زندانیان باید مطابق استانداردهای بین‌المللی تضمین شود",
            "اعدام باید لغو یا حداقل به شدت محدود شود",
            "بازداشت موقت طولانی‌مدت نقض حقوق بشر است",
            "استقلال وکلا و نهاد وکالت باید تضمین شود",
            "دادگاه‌ها باید علنی و شفاف برگزار شوند",
            "هیچ نهادی نباید بالاتر از قانون باشد",
        ],
        "en": [
            "The judiciary must be completely independent from the government",
            "Every defendant has the right to a lawyer and a fair trial",
            "Torture and arbitrary detention must be prohibited",
            "Judges must be selected based on merit and expertise",
            "Prisoner rights must be guaranteed per international standards",
            "The death penalty should be abolished or severely restricted",
            "Prolonged pretrial detention is a human rights violation",
            "The independence of lawyers and the bar association must be ensured",
            "Court proceedings must be open and transparent",
            "No institution should be above the law",
        ],
    },
    {
        "id": "housing",
        "fa": [
            "مسکن مناسب و مقرون به صرفه حق هر خانواده‌ای است",
            "قیمت مسکن باید با درآمد مردم متناسب باشد",
            "دولت باید ساخت مسکن اجتماعی را گسترش دهد",
            "سوداگری در بازار مسکن باید کنترل شود",
            "اجاره‌بها باید تنظیم و از مستاجران حمایت شود",
            "بی‌خانمانی باید با برنامه‌های جامع ریشه‌کن شود",
            "وام مسکن باید با شرایط آسان و سود پایین ارائه شود",
            "شهرسازی باید بر اساس نیاز واقعی مردم برنامه‌ریزی شود",
            "ساخت‌وساز غیرقانونی در حاشیه شهرها نشانه بحران مسکن است",
            "هر جوانی باید امکان خرید خانه را داشته باشد",
        ],
        "en": [
            "Affordable and adequate housing is every family's right",
            "Housing prices must be proportionate to people's income",
            "The government must expand social housing construction",
            "Speculation in the housing market must be controlled",
            "Rent must be regulated and tenants must be protected",
            "Homelessness must be eradicated through comprehensive programs",
            "Housing loans should be offered with easy terms and low interest",
            "Urban planning must be based on actual needs of the people",
            "Illegal construction on city outskirts signals a housing crisis",
            "Every young person should be able to afford a home",
        ],
    },
    {
        "id": "anticorruption",
        "fa": [
            "مبارزه با فساد باید اولویت اصلی حکومت باشد",
            "دارایی مقامات دولتی باید به صورت عمومی اعلام شود",
            "نهادهای نظارتی مستقل برای مبارزه با فساد ضروری هستند",
            "افشاگران فساد باید قانوناً حمایت شوند",
            "رشوه‌خواری در نهادهای دولتی باید ریشه‌کن شود",
            "شفافیت در بودجه‌ریزی و هزینه‌های دولتی الزامی است",
            "قراردادهای دولتی باید به صورت عمومی و شفاف منتشر شوند",
            "فساد اداری بزرگ‌ترین مانع پیشرفت کشور است",
            "مجازات‌های سنگین برای فساد اقتصادی باید اعمال شود",
            "دسترسی عمومی به اطلاعات دولتی حق شهروندان است",
        ],
        "en": [
            "Fighting corruption must be the government's top priority",
            "Assets of government officials must be publicly disclosed",
            "Independent oversight institutions are essential for combating corruption",
            "Whistleblowers must be legally protected",
            "Bribery in government institutions must be eradicated",
            "Transparency in government budgeting and spending is mandatory",
            "Government contracts must be publicly and transparently published",
            "Administrative corruption is the biggest obstacle to national progress",
            "Heavy penalties must be imposed for economic corruption",
            "Public access to government information is a citizen's right",
        ],
    },
]

_OUTLIERS: list[dict[str, str]] = [
    {"text": "برنامه فضایی ایران باید گسترش یابد", "lang": "fa"},
    {"text": "Animal rights legislation needs to be strengthened", "lang": "en"},
    {"text": "ورزشگاه‌های جدید باید در شهرهای کوچک ساخته شوند", "lang": "fa"},
    {"text": "Preserving historical monuments is vital for our cultural heritage", "lang": "en"},
    {"text": "سیستم حمل‌ونقل عمومی باید مدرن و کارآمد شود", "lang": "fa"},
    {"text": "Digital privacy laws need to be enacted urgently", "lang": "en"},
    {"text": "انرژی هسته‌ای صلح‌آمیز حق مسلم ایران است", "lang": "fa"},
    {"text": "Agricultural subsidies should be reformed for efficiency", "lang": "en"},
    {"text": "صنعت گردشگری باید توسعه یابد", "lang": "fa"},
    {"text": "Military spending should be reduced and redirected to education", "lang": "en"},
    {"text": "ورزش زنان باید بیشتر حمایت مالی شود", "lang": "fa"},
    {"text": "Libraries should receive more public funding", "lang": "en"},
    {"text": "هنرمندان باید از حمایت دولتی برخوردار شوند", "lang": "fa"},
    {"text": "Public parks and green spaces must be expanded in cities", "lang": "en"},
    {"text": "صنایع دستی ایرانی باید حمایت شود", "lang": "fa"},
    {"text": "Cycling infrastructure should be developed in urban areas", "lang": "en"},
    {"text": "زبان‌های محلی باید حفظ و ترویج شوند", "lang": "fa"},
    {"text": "Food safety regulations need to be stricter", "lang": "en"},
    {"text": "آموزش زبان خارجی باید از دوره ابتدایی آغاز شود", "lang": "fa"},
    {"text": "Senior citizen care facilities must be improved", "lang": "en"},
    {"text": "موزه‌های بیشتری باید ساخته شود", "lang": "fa"},
    {"text": "Organ donation awareness campaigns should be expanded", "lang": "en"},
    {"text": "حمایت از استعدادهای ورزشی ضروری است", "lang": "fa"},
    {"text": "Refugee rights must be respected and protected", "lang": "en"},
    {"text": "سینمای ایران باید بدون سانسور فعالیت کند", "lang": "fa"},
    {"text": "Recycling programs should be mandatory in all cities", "lang": "en"},
    {"text": "خدمات پستی باید بهبود یابد", "lang": "fa"},
    {"text": "Public Wi-Fi should be available in all major cities", "lang": "en"},
    {"text": "نگهداری از حیوانات خیابانی باید سازماندهی شود", "lang": "fa"},
    {"text": "Science research funding should be doubled", "lang": "en"},
    {"text": "بازارهای سنتی باید حفظ شوند", "lang": "fa"},
    {"text": "Electric vehicle adoption should be incentivized", "lang": "en"},
    {"text": "ایمنی جاده‌ها باید بهبود یابد", "lang": "fa"},
    {"text": "Telemedicine services should be expanded to rural areas", "lang": "en"},
    {"text": "خدمات کتابخانه‌ای باید رایگان باشد", "lang": "fa"},
    {"text": "Data center infrastructure should be developed domestically", "lang": "en"},
    {"text": "حمایت از کشاورزان کوچک ضروری است", "lang": "fa"},
    {"text": "Noise pollution regulations should be enforced", "lang": "en"},
    {"text": "تئاتر و هنرهای نمایشی باید حمایت شوند", "lang": "fa"},
    {"text": "Childhood vaccination programs must remain universal", "lang": "en"},
    {"text": "فرودگاه‌های منطقه‌ای باید توسعه یابند", "lang": "fa"},
    {"text": "Endangered plant species need protection programs", "lang": "en"},
    {"text": "آموزش فنی و حرفه‌ای باید تقویت شود", "lang": "fa"},
    {"text": "Disaster preparedness programs need more investment", "lang": "en"},
    {"text": "میراث فرهنگی ناملموس باید ثبت و حفظ شود", "lang": "fa"},
    {"text": "Genetic research ethics guidelines should be established", "lang": "en"},
    {"text": "حمل‌ونقل ریلی باید توسعه یابد", "lang": "fa"},
    {"text": "Beekeeping and pollinator protection should be supported", "lang": "en"},
    {"text": "کیفیت نان باید بهبود یابد", "lang": "fa"},
    {"text": "Astronomy education should be promoted in schools", "lang": "en"},
]

CLUSTER_IDS = [str(c["id"]) for c in _CLUSTERS]


def generate_inputs() -> list[dict[str, str]]:
    """Return ~1050 test inputs with expected cluster labels.

    Each item: {"text": str, "language": "fa"|"en", "expected_cluster": str|None}
    """
    inputs: list[dict[str, str]] = []

    for cluster in _CLUSTERS:
        cluster_id = str(cluster["id"])
        for base in cluster["fa"]:  # type: ignore[union-attr]
            for variation in _VARIATIONS_FA:
                inputs.append({
                    "text": variation.format(base=base),
                    "language": "fa",
                    "expected_cluster": cluster_id,
                })
        for base in cluster["en"]:  # type: ignore[union-attr]
            for variation in _VARIATIONS_EN:
                inputs.append({
                    "text": variation.format(base=base),
                    "language": "en",
                    "expected_cluster": cluster_id,
                })

    for outlier in _OUTLIERS:
        inputs.append({
            "text": outlier["text"],
            "language": outlier["lang"],
            "expected_cluster": "",
        })

    return inputs

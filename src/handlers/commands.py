from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.rate_limit import check_voice_rate_limit
from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.config import get_settings
from src.db.queries import count_cluster_endorsements, get_user_endorsed_cluster_ids
from src.handlers.intake import handle_submission
from src.handlers.voting import cast_vote, record_endorsement
from src.models.cluster import Cluster
from src.models.policy_option import PolicyOption
from src.models.user import User
from src.models.vote import VotingCycle
from src.voice.enrollment import (
    finalize_enrollment,
    get_current_phrase,
    process_enrollment_audio,
    start_enrollment,
)
from src.voice.verification import pick_verification_phrase, verify_voice

# ---------------------------------------------------------------------------
# Pre-auth messages (bilingual — user locale unknown)
# ---------------------------------------------------------------------------
REGISTER_HINT = (
    "If you have not signed up on our website, please sign up at {url} and get your verification code.\n"
    "If you have your verification code, please paste it here.\n\n"
    "اگر در وبسایت ما ثبت‌نام نکرده‌اید، لطفاً در {url} ثبت‌نام کنید و کد تأیید خود را دریافت کنید.\n"
    "اگر کد تأیید خود را دارید، لطفاً آن را اینجا وارد کنید."
)
USER_ALREADY_LINKED = (
    "⚠️ Your email is already linked to another Telegram account.\n"
    "If you need to change it, please contact support.\n\n"
    "⚠️ حساب ایمیل شما قبلاً به یک اکانت تلگرام دیگر متصل شده است.\n"
    "اگر نیاز به تغییر دارید، لطفاً با پشتیبانی تماس بگیرید."
)
ACCOUNT_ALREADY_LINKED = (
    "⚠️ This Telegram account is already linked to another email.\n"
    "Each Telegram account can only be linked to one email.\n\n"
    "⚠️ این اکانت تلگرام قبلاً به یک ایمیل دیگر متصل شده است.\n"
    "هر اکانت تلگرام فقط می‌تواند به یک ایمیل متصل باشد."
)

# ---------------------------------------------------------------------------
# Welcome message (locale-aware, sent after successful account linking)
# ---------------------------------------------------------------------------
_WELCOME: dict[str, str] = {
    "fa": (
        "✅ حساب شما با موفقیت متصل شد! ({email})\n\n"
        "به «اراده جمعی» خوش آمدید!\n"
        "اینجا می‌توانید نگرانی‌ها و پیشنهادهای سیاستی خود را ارسال کنید. "
        "هوش مصنوعی پیام شما را ساختاربندی می‌کند، موارد مشابه را گروه‌بندی می‌کند، "
        "و جامعه با رأی‌گیری اولویت‌ها را مشخص می‌کند."
    ),
    "en": (
        "✅ Your account has been linked successfully! ({email})\n\n"
        "Welcome to Collective Will!\n"
        "Here you can submit your policy concerns and proposals. "
        "AI will structure your message, group similar ideas together, "
        "and the community votes to set priorities."
    ),
}

# ---------------------------------------------------------------------------
# Locale-aware messages (post-auth)
# ---------------------------------------------------------------------------
_MESSAGES: dict[str, dict[str, str]] = {
    "fa": {
        "submission_prompt": "📝 لطفاً نگرانی یا پیشنهاد سیاستی خود را بنویسید:",
        "menu_hint": "لطفاً از دکمه‌های زیر استفاده کنید.",
        "no_active_cycle": (
            "در حال حاضر رای‌گیری فعالی وجود ندارد.\n\n"
            "رای‌گیری زمانی آغاز می‌شود که سیاست‌های کافی توسط شهروندان امضا شده باشند. "
            "می‌توانید با امضای سیاست‌ها به شروع زودتر رای‌گیری کمک کنید!"
        ),
        "endorsement_header": (
            "موضوعات زیر برای رای‌گیری بعدی در نظر گرفته شده‌اند.\n"
            "روی هر کدام که می‌خواهید در رای‌گیری باشد ضربه بزنید:"
        ),
        "ballot_header": "🗳️ سیاست {n} از {total}: ",
        "vote_recorded": "✅ رای شما ثبت شد!",
        "vote_rejected": "رای رد شد: {reason}",
        "endorsement_recorded": "✅ امضای شما ثبت شد.",
        "lang_changed": "Language changed to English.",
        "analytics_link": "📊 مشاهده در وبسایت: {url}",
        "endorse_btn": "امضا {n}",
        "submit_vote_btn": "✅ ثبت رای",
        "back_btn": "بازگشت",
        "cancel_btn": "انصراف",
        "skip_btn": "⏭️ رد شدن",
        "prev_btn": "⬅️ قبلی",
        "change_btn": "✏️ تغییر پاسخ‌ها",
        "options_header": "موضع خود را انتخاب کنید:",
        "summary_header": "📊 خلاصه انتخاب‌های شما:\n",
        "skipped_label": "⏭️ رد شده",
        "no_options": "گزینه‌ای برای این سیاست موجود نیست.",
        "no_endorsable_clusters": "در حال حاضر سیاستی برای امضا وجود ندارد.",
        "endorse_policy_header": "✍️ سیاست {n} از {total}:",
        "endorse_complete": "✅ همه سیاست‌ها بررسی شدند!",
        "cycle_timing": "🗳️ رای‌گیری فعال — {policies} سیاست\n⏰ پایان: {ends_at}\n",
        # Voice enrollment
        "voice_enroll_choose_lang": (
            "🎤 ثبت صدا برای تأیید هویت\n\n"
            "برای امنیت و اصل «یک نفر، یک رای» باید صدای شما را ثبت کنیم.\n"
            "شما {total} عبارت کوتاه را با صدای بلند می‌خوانید.\n\n"
            "زبان عبارات را انتخاب کنید:\n\n"
            "🎤 Voice registration\n\n"
            "To keep the process secure, we need to register your voice.\n"
            "You'll read {total} short phrases aloud.\n\n"
            "Choose your phrase language:"
        ),
        "voice_enroll_start": (
            "🎤 ثبت صدا برای تأیید هویت\n\n"
            "برای اینکه بتوانیم هنگام ارسال پیشنهاد یا رای تأیید کنیم که شما هستید، باید صدای شما را ثبت کنیم. "
            "این کار به امنیت و اصل «یک نفر، یک رای» کمک می‌کند.\n\n"
            "کار شما: {total} عبارت کوتاه را با صدای بلند بخوانید و هر کدام را به صورت پیام صوتی ارسال کنید. "
            "ما از اینها پروفایل صوتی شما را می‌سازیم تا بعداً هویت شما را تأیید کنیم.\n\n"
            "عبارت {step} از {total}:\n«{phrase}»"
        ),
        "voice_enroll_intro": (
            "🎤 لطفاً عبارت زیر را با صدای بلند بخوانید و ضبط صوتی ارسال کنید:\n\n"
            "«{phrase}»\n\n"
            "(عبارت {step} از {total})"
        ),
        "voice_enroll_accepted": (
            "✅ عبارت پذیرفته شد! لطفاً عبارت بعدی را بخوانید:\n\n"
            "«{phrase}»\n\n(عبارت {step} از {total})"
        ),
        "voice_enroll_retry": (
            "❌ متوجه نشدیم. لطفاً دوباره عبارت را بخوانید:\n\n"
            "«{phrase}»\n\n(تلاش {attempt} از {max_attempts})"
        ),
        "voice_enroll_replaced": "عبارت جدید:\n\n«{phrase}»\n\nلطفاً این عبارت را بخوانید.",
        "voice_enroll_complete": "✅ ثبت صوتی شما با موفقیت انجام شد!",
        "voice_enroll_blocked": "❌ تلاش‌های زیادی ناموفق بود. لطفاً فردا دوباره امتحان کنید.",
        "voice_enroll_error": "⚠️ خطا در پردازش صدا. لطفاً دوباره تلاش کنید.",
        "voice_enroll_needed": "🎤 لطفاً ابتدا هویت صوتی خود را ثبت کنید. یک پیام صوتی ارسال کنید.",
        # Voice verification
        "voice_verify_prompt": "🔒 لطفاً برای تأیید هویت، عبارت زیر را بخوانید:\n\n«{phrase}»",
        "voice_verify_success": "✅ هویت شما تأیید شد!",
        "voice_verify_failed": "❌ تأیید صوتی ناموفق بود. لطفاً دوباره تلاش کنید.",
        "voice_technical_error": "⚠️ خطا در پردازش صدا. کد: {code}. لطفاً دوباره تلاش کنید.",
        "voice_verify_rate_limited": "⚠️ تعداد تلاش‌های مجاز شما تمام شده. لطفاً بعداً دوباره امتحان کنید.",
        "voice_verify_nudge": "🔒 لطفاً یک پیام صوتی ارسال کنید تا هویت شما تأیید شود.",
        "voice_audio_too_short": "⚠️ پیام صوتی خیلی کوتاه است. لطفاً حداقل ۱ ثانیه ضبط کنید.",
        "voice_audio_too_long": "⚠️ پیام صوتی خیلی طولانی است. لطفاً حداکثر ۱۰ ثانیه ضبط کنید.",
        "voice_processing": "⏳ پیام صوتی شما دریافت شد. لطفاً تا ۱۵ ثانیه صبر کنید تا پردازش شود...",
    },
    "en": {
        "submission_prompt": "📝 Please type your concern or policy proposal:",
        "menu_hint": "Please use the buttons below.",
        "no_active_cycle": (
            "There is no active vote at this time.\n\n"
            "Voting begins once enough policies have been endorsed by citizens. "
            "You can help start the next vote sooner by endorsing policies!"
        ),
        "endorsement_header": (
            "These topics are being considered for the next vote.\n"
            "Tap to endorse ones you want on the ballot:"
        ),
        "ballot_header": "🗳️ Policy {n} of {total}: ",
        "vote_recorded": "✅ Your vote has been recorded!",
        "vote_rejected": "Vote rejected: {reason}",
        "endorsement_recorded": "✅ Your endorsement has been recorded.",
        "lang_changed": "زبان به فارسی تغییر کرد.",
        "analytics_link": "📊 View on website: {url}",
        "endorse_btn": "Endorse {n}",
        "submit_vote_btn": "✅ Submit vote",
        "back_btn": "Back",
        "cancel_btn": "Cancel",
        "skip_btn": "⏭️ Skip",
        "prev_btn": "⬅️ Previous",
        "change_btn": "✏️ Change answers",
        "options_header": "Choose your position:",
        "summary_header": "📊 Your selections:\n",
        "skipped_label": "⏭️ Skipped",
        "no_options": "No options available for this policy.",
        "no_endorsable_clusters": "No policies available for endorsement right now.",
        "endorse_policy_header": "✍️ Policy {n} of {total}:",
        "endorse_complete": "✅ All policies reviewed!",
        "cycle_timing": "🗳️ Active vote — {policies} policies\n⏰ Ends: {ends_at}\n",
        # Voice enrollment
        "voice_enroll_choose_lang": (
            "🎤 Voice registration\n\n"
            "To keep the process secure, we need to register your voice.\n"
            "You'll read {total} short phrases aloud.\n\n"
            "Choose your phrase language:\n\n"
            "🎤 ثبت صدا برای تأیید هویت\n\n"
            "برای امنیت و اصل «یک نفر، یک رای» باید صدای شما را ثبت کنیم.\n"
            "شما {total} عبارت کوتاه را با صدای بلند می‌خوانید.\n\n"
            "زبان عبارات را انتخاب کنید:"
        ),
        "voice_enroll_start": (
            "🎤 Voice registration for identity verification\n\n"
            "We need to register your voice so we can verify it's you when you submit proposals or vote. "
            "This keeps the process secure and ensures one person, one voice.\n\n"
            "What you'll do: You'll read {total} short phrases aloud and send each as a voice message. "
            "We use these to create your voice profile for future verification.\n\n"
            "Phrase {step} of {total}:\n\"{phrase}\""
        ),
        "voice_enroll_intro": (
            "🎤 Please read the following phrase aloud and send a voice message:\n\n"
            "\"{phrase}\"\n\n"
            "(Phrase {step} of {total})"
        ),
        "voice_enroll_accepted": (
            "✅ Phrase accepted! Please read the next phrase:\n\n"
            "\"{phrase}\"\n\n(Phrase {step} of {total})"
        ),
        "voice_enroll_retry": (
            "❌ We couldn't understand. Please read the phrase again:\n\n"
            "\"{phrase}\"\n\n(Attempt {attempt} of {max_attempts})"
        ),
        "voice_enroll_replaced": "New phrase:\n\n\"{phrase}\"\n\nPlease read this phrase.",
        "voice_enroll_complete": "✅ Your voice enrollment is complete!",
        "voice_enroll_blocked": "❌ Too many failed attempts. Please try again tomorrow.",
        "voice_enroll_error": "⚠️ Error processing audio. Please try again.",
        "voice_enroll_needed": "🎤 Please complete voice enrollment first. Send a voice message.",
        # Voice verification
        "voice_verify_prompt": "🔒 To verify your identity, please read the following phrase:\n\n\"{phrase}\"",
        "voice_verify_success": "✅ Your identity has been verified!",
        "voice_verify_failed": "❌ Voice verification failed. Please try again.",
        "voice_technical_error": "⚠️ Error processing audio. Code: {code}. Please try again.",
        "voice_verify_rate_limited": "⚠️ Too many attempts. Please try again later.",
        "voice_verify_nudge": "🔒 Please send a voice message to verify your identity.",
        "voice_audio_too_short": "⚠️ Voice message too short. Please record at least 1 second.",
        "voice_audio_too_long": "⚠️ Voice message too long. Please keep it under 10 seconds.",
        "voice_processing": "⏳ Voice message received. Please wait up to 15 seconds while it is processed...",
    },
}

_OPTION_LETTERS = "ABCDEFGHIJ"

_FARSI_DIGITS_TABLE = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _format_cycle_end(ends_at: datetime, locale: str) -> str:
    """Human-readable remaining time for cycle end."""
    remaining = ends_at - datetime.now(UTC)
    total_hours = max(0, remaining.total_seconds()) / 3600
    if total_hours >= 24:
        days = int(total_hours // 24)
        hours = int(total_hours % 24)
        if locale == "fa":
            d = str(days).translate(_FARSI_DIGITS_TABLE)
            h = str(hours).translate(_FARSI_DIGITS_TABLE)
            return f"{d} روز و {h} ساعت دیگر"
        return f"in {days}d {hours}h"
    if total_hours >= 1:
        hours = int(total_hours)
        if locale == "fa":
            return f"{str(hours).translate(_FARSI_DIGITS_TABLE)} ساعت دیگر"
        return f"in {hours}h"
    minutes = max(1, int(total_hours * 60))
    if locale == "fa":
        return f"{str(minutes).translate(_FARSI_DIGITS_TABLE)} دقیقه دیگر"
    return f"in {minutes}m"


def _msg(locale: str, key: str, **kwargs: str | int) -> str:
    lang = locale if locale in _MESSAGES else "en"
    template = _MESSAGES[lang][key]
    return template.format(**kwargs) if kwargs else template


# ---------------------------------------------------------------------------
# Main menu inline keyboard
# ---------------------------------------------------------------------------
_MAIN_MENU: dict[str, dict[str, list[list[dict[str, str]]]]] = {
    "fa": {
        "inline_keyboard": [
            [{"text": "📝 ارسال نگرانی", "callback_data": "submit"}],
            [{"text": "✍️ امضای سیاست", "callback_data": "endorse"}],
            [{"text": "🗳️ رای دادن", "callback_data": "vote"}],
            [{"text": "🌐 Change language", "callback_data": "lang"}],
        ]
    },
    "en": {
        "inline_keyboard": [
            [{"text": "📝 Submit a concern", "callback_data": "submit"}],
            [{"text": "✍️ Endorse policies", "callback_data": "endorse"}],
            [{"text": "🗳️ Vote", "callback_data": "vote"}],
            [{"text": "🌐 تغییر زبان", "callback_data": "lang"}],
        ]
    },
}


def _main_menu_markup(locale: str) -> dict[str, list[list[dict[str, str]]]]:
    return _MAIN_MENU.get(locale, _MAIN_MENU["en"])


def _cancel_keyboard(locale: str) -> dict[str, list[list[dict[str, str]]]]:
    return {"inline_keyboard": [[{"text": _msg(locale, "cancel_btn"), "callback_data": "cancel"}]]}


def _voice_lang_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    """Language choice keyboard for voice enrollment/verification."""
    return {"inline_keyboard": [[
        {"text": "🇬🇧 English", "callback_data": "vlang_en"},
        {"text": "🇮🇷 فارسی", "callback_data": "vlang_fa"},
    ]]}


def _voice_enroll_keyboard(locale: str) -> dict[str, list[list[dict[str, str]]]]:
    """Enrollment message keyboard: language switch button."""
    lang_text = "🌐 فارسی" if locale == "en" else "🌐 English"
    other = "fa" if locale == "en" else "en"
    return {"inline_keyboard": [[{"text": lang_text, "callback_data": f"vlang_{other}"}]]}


def _voice_verify_keyboard(locale: str) -> dict[str, list[list[dict[str, str]]]]:
    """Verification message keyboard: cancel + language switch."""
    lang_text = "🌐 فارسی" if locale == "en" else "🌐 English"
    other = "fa" if locale == "en" else "en"
    return {"inline_keyboard": [
        [{"text": _msg(locale, "cancel_btn"), "callback_data": "cancel"}],
        [{"text": lang_text, "callback_data": f"vlang_{other}"}],
    ]}


# ---------------------------------------------------------------------------
# Endorsement keyboard builder
# ---------------------------------------------------------------------------

def _build_endorsement_keyboard(
    locale: str, idx: int, total: int
) -> dict[str, list[list[dict[str, str]]]]:
    """Per-cluster endorsement keyboard with Endorse/Skip/Back/Cancel."""
    rows: list[list[dict[str, str]]] = []
    rows.append([{
        "text": _msg(locale, "endorse_btn", n=idx + 1),
        "callback_data": f"e:{idx + 1}",
    }])
    nav: list[dict[str, str]] = []
    if idx > 0:
        nav.append({"text": _msg(locale, "prev_btn"), "callback_data": "ebk"})
    nav.append({"text": _msg(locale, "skip_btn"), "callback_data": "esk"})
    rows.append(nav)
    rows.append([{"text": _msg(locale, "cancel_btn"), "callback_data": "main"}])
    return {"inline_keyboard": rows}


# ---------------------------------------------------------------------------
# Per-policy voting helpers
# ---------------------------------------------------------------------------

def _build_policy_keyboard(
    locale: str,
    options: list[PolicyOption],
    current_idx: int,
    total: int,
) -> dict[str, list[list[dict[str, str]]]]:
    """Build inline keyboard for a single policy's stance options."""
    rows: list[list[dict[str, str]]] = []

    for i, opt in enumerate(options):
        letter = _OPTION_LETTERS[i] if i < len(_OPTION_LETTERS) else str(i + 1)
        label = opt.label_en if locale == "en" and opt.label_en else opt.label
        rows.append([{"text": f"{letter}. {label}", "callback_data": f"vo:{i + 1}"}])

    nav_row: list[dict[str, str]] = []
    if current_idx > 0:
        nav_row.append({"text": _msg(locale, "prev_btn"), "callback_data": "vbk"})
    nav_row.append({"text": _msg(locale, "skip_btn"), "callback_data": "vsk"})
    rows.append(nav_row)

    rows.append([{"text": _msg(locale, "cancel_btn"), "callback_data": "main"}])

    return {"inline_keyboard": rows}


def _build_summary_keyboard(
    locale: str,
) -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [{"text": _msg(locale, "submit_vote_btn"), "callback_data": "vsub"}],
            [{"text": _msg(locale, "change_btn"), "callback_data": "vchg"}],
            [{"text": _msg(locale, "cancel_btn"), "callback_data": "main"}],
        ]
    }


def _format_policy_message(
    locale: str,
    cluster: Cluster,
    options: list[PolicyOption],
    current_idx: int,
    total: int,
) -> str:
    """Format message text showing a single policy with its options."""
    summary = cluster.summary
    header = _msg(locale, "ballot_header", n=current_idx + 1, total=total)
    lines = [f"{header}\n\n{summary}\n"]

    if not options:
        lines.append(_msg(locale, "no_options"))
        return "\n".join(lines)

    lines.append(f"\n{_msg(locale, 'options_header')}\n")

    for i, opt in enumerate(options):
        letter = _OPTION_LETTERS[i] if i < len(_OPTION_LETTERS) else str(i + 1)
        label = opt.label_en if locale == "en" and opt.label_en else opt.label
        desc = opt.description_en if locale == "en" and opt.description_en else opt.description
        lines.append(f"{letter}. {label}\n{desc}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Menu and prompt senders
# ---------------------------------------------------------------------------

async def _send_main_menu(
    locale: str, recipient_ref: str, channel: BaseChannel,
) -> None:
    await channel.send_message(OutboundMessage(
        recipient_ref=recipient_ref,
        text=_msg(locale, "menu_hint"),
        reply_markup=_main_menu_markup(locale),
    ))


# ---------------------------------------------------------------------------
# Voting session state helpers
# ---------------------------------------------------------------------------

def _init_vote_session(
    cycle_id: UUID, cluster_ids: list[UUID]
) -> dict[str, Any]:
    return {
        "cycle_id": str(cycle_id),
        "cluster_ids": [str(c) for c in cluster_ids],
        "current_idx": 0,
        "selections": {},
    }


def _get_vote_session(user: User) -> dict[str, Any] | None:
    data = user.bot_state_data
    if data and isinstance(data, dict) and data.get("cycle_id"):
        return copy.deepcopy(data)
    return None


async def _load_cluster_with_options(
    db: AsyncSession, cluster_id: UUID
) -> tuple[Cluster | None, list[PolicyOption]]:
    result = await db.execute(
        select(Cluster)
        .where(Cluster.id == cluster_id)
        .options(selectinload(Cluster.options))
    )
    cluster = result.scalar_one_or_none()
    if cluster is None:
        return None, []
    opts = sorted(cluster.options, key=lambda o: o.position)
    return cluster, opts


async def _show_current_policy(
    user: User,
    message: UnifiedMessage,
    channel: BaseChannel,
    db: AsyncSession,
    session_data: dict[str, Any],
) -> str:
    """Display the current policy in the voting sequence."""
    idx = session_data["current_idx"]
    cluster_ids = session_data["cluster_ids"]
    total = len(cluster_ids)

    if idx >= total:
        return await _show_vote_summary(user, message, channel, db, session_data)

    cluster_id = UUID(cluster_ids[idx])
    cluster, options = await _load_cluster_with_options(db, cluster_id)
    if cluster is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "cluster_not_found"

    text = _format_policy_message(user.locale, cluster, options, idx, total)
    keyboard = _build_policy_keyboard(user.locale, options, idx, total)

    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=text,
        reply_markup=keyboard,
    ))
    return "policy_shown"


async def _show_vote_summary(
    user: User,
    message: UnifiedMessage,
    channel: BaseChannel,
    db: AsyncSession,
    session_data: dict[str, Any],
) -> str:
    """Show a summary of selections, auto-submit, and return to main menu."""
    locale = user.locale
    cluster_ids = session_data["cluster_ids"]
    selections = session_data.get("selections", {})

    lines = [_msg(locale, "summary_header")]

    option_cache: dict[str, PolicyOption] = {}
    for cid_str in cluster_ids:
        cluster_id = UUID(cid_str)
        cluster, options = await _load_cluster_with_options(db, cluster_id)
        if cluster is None:
            continue
        for opt in options:
            option_cache[str(opt.id)] = opt

    for i, cid_str in enumerate(cluster_ids, 1):
        cluster_id = UUID(cid_str)
        cluster_result = await db.execute(select(Cluster).where(Cluster.id == cluster_id))
        cluster = cluster_result.scalar_one_or_none()
        if cluster is None:
            continue
        summary = cluster.summary
        short_summary = summary[:60] + "..." if len(summary) > 60 else summary

        selected_option_id = selections.get(cid_str)
        if selected_option_id:
            selected_opt = option_cache.get(selected_option_id)
            if selected_opt:
                opt_label = (
                    selected_opt.label_en
                    if locale == "en" and selected_opt.label_en
                    else selected_opt.label
                )
                lines.append(f"{i}. {short_summary}\n   ✅ {opt_label}")
            else:
                lines.append(f"{i}. {short_summary}\n   ✅ (selected)")
        else:
            lines.append(
                f"{i}. {short_summary}\n"
                f"   {_msg(locale, 'skipped_label')}"
            )

    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text="\n".join(lines),
    ))

    cycle_id = UUID(session_data["cycle_id"])
    cycle_result = await db.execute(
        select(VotingCycle).where(VotingCycle.id == cycle_id)
    )
    cycle = cycle_result.scalar_one_or_none()
    if cycle is None or cycle.status != "active":
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(locale, "no_active_cycle"),
        ))
        user.bot_state = None
        user.bot_state_data = None
        await db.commit()
        await _send_main_menu(locale, message.sender_ref, channel)
        return "no_active_cycle"

    selections_list = [
        {"cluster_id": cid, "option_id": oid}
        for cid, oid in selections.items()
        if oid
    ]

    if not selections_list:
        user.bot_state = None
        user.bot_state_data = None
        await db.commit()
        await _send_main_menu(locale, message.sender_ref, channel)
        return "empty_vote"

    settings = get_settings()
    vote, status = await cast_vote(
        session=db,
        user=user,
        cycle=cycle,
        selections=selections_list,
        min_account_age_hours=settings.min_account_age_hours,
        require_contribution=settings.require_contribution_for_vote,
    )

    user.bot_state = None
    user.bot_state_data = None
    await db.commit()

    if vote is None:
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(locale, "vote_rejected", reason=status),
        ))
        await _send_main_menu(locale, message.sender_ref, channel)
        return status

    # Extend voice session on successful vote
    if user.is_voice_enrolled:
        user.voice_verified_at = datetime.now(UTC)
        await db.commit()

    base_url = settings.app_public_base_url
    analytics_url = f"{base_url}/{locale}/collective-concerns/community-votes"
    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=(
            f"{_msg(locale, 'vote_recorded')}\n"
            f"{_msg(locale, 'analytics_link', url=analytics_url)}"
        ),
    ))
    await _send_main_menu(locale, message.sender_ref, channel)
    return "vote_recorded"


# ---------------------------------------------------------------------------
# Endorsement session helpers
# ---------------------------------------------------------------------------

def _init_endorse_session(cluster_ids: list[UUID]) -> dict[str, Any]:
    return {
        "endorsing": True,
        "cluster_ids": [str(c) for c in cluster_ids],
        "current_idx": 0,
    }


def _get_endorse_session(user: User) -> dict[str, Any] | None:
    data = user.bot_state_data
    if data and isinstance(data, dict) and data.get("endorsing"):
        return copy.deepcopy(data)
    return None


async def _show_endorsement_policy(
    user: User,
    message: UnifiedMessage,
    channel: BaseChannel,
    db: AsyncSession,
    session_data: dict[str, Any],
) -> str:
    """Display one cluster for endorsement."""
    idx = session_data["current_idx"]
    cluster_ids = session_data["cluster_ids"]
    total = len(cluster_ids)

    if idx >= total:
        user.bot_state = None
        user.bot_state_data = None
        await db.commit()
        await channel.edit_message_markup(
            message.sender_ref, message.message_id, {"inline_keyboard": []},
        )
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "endorse_complete"),
        ))
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "endorse_done"

    cluster_id = UUID(cluster_ids[idx])
    result = await db.execute(select(Cluster).where(Cluster.id == cluster_id))
    cluster = result.scalar_one_or_none()
    if cluster is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "cluster_not_found"

    locale = user.locale

    if locale == "fa" and cluster.ballot_question_fa:
        question = cluster.ballot_question_fa
    else:
        question = cluster.ballot_question or cluster.summary

    endorsement_count = await count_cluster_endorsements(db, cluster_id)
    header = _msg(locale, "endorse_policy_header", n=idx + 1, total=total)
    lines = [header, "", question, ""]
    lines.append(f"👥 {cluster.member_count} | ✍️ {endorsement_count}")

    keyboard = _build_endorsement_keyboard(locale, idx, total)

    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text="\n".join(lines),
        reply_markup=keyboard,
    ))
    return "endorse_policy_shown"


async def _handle_endorse_menu(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Show endorsable pre-ballot clusters."""
    cluster_result = await db.execute(
        select(Cluster)
        .where(Cluster.ballot_question.isnot(None), Cluster.status == "open")
        .order_by(Cluster.created_at)
    )
    all_clusters = list(cluster_result.scalars().all())

    cycle_result = await db.execute(
        select(VotingCycle.cluster_ids)
        .where(VotingCycle.status == "active")
    )
    active_ids: set[UUID] = set()
    for row in cycle_result.all():
        if row[0]:
            active_ids.update(row[0])

    endorsable = [c for c in all_clusters if c.id not in active_ids]
    endorsable_ids = [c.id for c in endorsable]
    already_endorsed = await get_user_endorsed_cluster_ids(db, user.id, endorsable_ids)
    not_yet_endorsed = [c for c in endorsable if c.id not in already_endorsed]

    if not not_yet_endorsed:
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "no_endorsable_clusters"),
        ))
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_endorsable_clusters"

    cluster_ids = [c.id for c in not_yet_endorsed]

    session_data = _init_endorse_session(cluster_ids)
    user.bot_state = "endorsing"
    user.bot_state_data = session_data
    await db.commit()

    return await _show_endorsement_policy(user, message, channel, db, session_data)


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------

async def _handle_submit_callback(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    user.bot_state = "awaiting_submission"
    await db.commit()
    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(user.locale, "submission_prompt"),
        reply_markup=_cancel_keyboard(user.locale),
    ))
    return "awaiting_submission"


async def _handle_vote_callback(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Start the per-policy voting flow."""
    cycle_result = await db.execute(
        select(VotingCycle)
        .where(VotingCycle.status == "active")
        .order_by(VotingCycle.started_at.desc())
    )
    active_cycle = cycle_result.scalars().first()

    if active_cycle is None or not active_cycle.cluster_ids:
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "no_active_cycle"),
        ))
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_active_cycle"

    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(
            user.locale,
            "cycle_timing",
            policies=str(len(active_cycle.cluster_ids)),
            ends_at=_format_cycle_end(active_cycle.ends_at, user.locale),
        ),
    ))

    session_data = _init_vote_session(active_cycle.id, active_cycle.cluster_ids)
    user.bot_state = "voting"
    user.bot_state_data = session_data
    await db.commit()

    return await _show_current_policy(user, message, channel, db, session_data)


async def _handle_lang_callback(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    old_locale = user.locale
    user.locale = "en" if old_locale == "fa" else "fa"
    await db.commit()
    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(old_locale, "lang_changed"),
    ))
    await _send_main_menu(user.locale, message.sender_ref, channel)
    return "language_updated"


async def _handle_option_select(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """User selected a stance option for the current policy."""
    session_data = _get_vote_session(user)
    if session_data is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_vote_session"

    parts = (message.callback_data or "").split(":")
    if len(parts) != 2:
        return "invalid_option"
    try:
        option_pos = int(parts[1])
    except ValueError:
        return "invalid_option"

    idx = session_data["current_idx"]
    cluster_ids = session_data["cluster_ids"]
    if idx >= len(cluster_ids):
        return "invalid_state"

    cluster_id = UUID(cluster_ids[idx])
    _, options = await _load_cluster_with_options(db, cluster_id)

    if option_pos < 1 or option_pos > len(options):
        return "invalid_option_index"

    selected_option = options[option_pos - 1]
    session_data["selections"][cluster_ids[idx]] = str(selected_option.id)
    session_data["current_idx"] = idx + 1

    user.bot_state_data = session_data
    await db.commit()

    return await _show_current_policy(user, message, channel, db, session_data)


async def _handle_skip_cluster(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Skip the current policy without selecting an option."""
    session_data = _get_vote_session(user)
    if session_data is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_vote_session"

    idx = session_data["current_idx"]
    cluster_ids = session_data["cluster_ids"]
    if idx >= len(cluster_ids):
        return "invalid_state"

    session_data["selections"].pop(cluster_ids[idx], None)
    session_data["current_idx"] = idx + 1

    user.bot_state_data = session_data
    await db.commit()

    return await _show_current_policy(user, message, channel, db, session_data)


async def _handle_vote_back(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Go back to the previous policy."""
    session_data = _get_vote_session(user)
    if session_data is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_vote_session"

    idx = session_data["current_idx"]
    if idx <= 0:
        return await _show_current_policy(user, message, channel, db, session_data)

    session_data["current_idx"] = idx - 1
    user.bot_state_data = session_data
    await db.commit()

    return await _show_current_policy(user, message, channel, db, session_data)


async def _handle_vote_change(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Go back to the first policy to change answers."""
    session_data = _get_vote_session(user)
    if session_data is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_vote_session"

    session_data["current_idx"] = 0
    user.bot_state_data = session_data
    await db.commit()

    return await _show_current_policy(user, message, channel, db, session_data)


async def _handle_vote_submit(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Submit the per-policy vote with all selections."""
    session_data = _get_vote_session(user)
    if session_data is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_vote_session"

    cycle_id = UUID(session_data["cycle_id"])
    cycle_result = await db.execute(
        select(VotingCycle).where(VotingCycle.id == cycle_id)
    )
    cycle = cycle_result.scalar_one_or_none()
    if cycle is None or cycle.status != "active":
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "no_active_cycle"),
        ))
        user.bot_state = None
        user.bot_state_data = None
        await db.commit()
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_active_cycle"

    raw_selections = session_data.get("selections", {})
    selections_list = [
        {"cluster_id": cid, "option_id": oid}
        for cid, oid in raw_selections.items()
        if oid
    ]

    if not selections_list:
        user.bot_state = None
        user.bot_state_data = None
        await db.commit()
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "empty_vote"

    settings = get_settings()
    vote, status = await cast_vote(
        session=db,
        user=user,
        cycle=cycle,
        selections=selections_list,
        min_account_age_hours=settings.min_account_age_hours,
        require_contribution=settings.require_contribution_for_vote,
    )

    user.bot_state = None
    user.bot_state_data = None
    await db.commit()

    if vote is None:
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "vote_rejected", reason=status),
        ))
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return status

    base_url = settings.app_public_base_url
    analytics_url = f"{base_url}/{user.locale}/collective-concerns/community-votes"
    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=(
            f"{_msg(user.locale, 'vote_recorded')}\n"
            f"{_msg(user.locale, 'analytics_link', url=analytics_url)}"
        ),
    ))
    await _send_main_menu(user.locale, message.sender_ref, channel)
    return "vote_recorded"


async def _handle_endorse(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Endorse a specific cluster from the endorsement session."""
    session_data = _get_endorse_session(user)
    if session_data is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_endorse_session"

    parts = (message.callback_data or "").split(":")
    if len(parts) != 2:
        return "invalid_endorse"
    try:
        index = int(parts[1])
    except ValueError:
        return "invalid_endorse"

    cluster_ids = session_data["cluster_ids"]
    if index < 1 or index > len(cluster_ids):
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "invalid_index"

    cluster_id = UUID(cluster_ids[index - 1])
    ok, status = await record_endorsement(session=db, user=user, cluster_id=cluster_id)
    if ok:
        # Extend voice session on successful endorsement
        if user.is_voice_enrolled:
            user.voice_verified_at = datetime.now(UTC)
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "endorsement_recorded"),
        ))

    session_data["current_idx"] = index
    user.bot_state_data = session_data
    await db.commit()

    return await _show_endorsement_policy(user, message, channel, db, session_data)


async def _handle_endorse_skip(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Skip the current cluster without endorsing."""
    session_data = _get_endorse_session(user)
    if session_data is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_endorse_session"

    session_data["current_idx"] = session_data["current_idx"] + 1
    user.bot_state_data = session_data
    await db.commit()

    return await _show_endorsement_policy(user, message, channel, db, session_data)


async def _handle_endorse_back(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    """Go back to the previous cluster in the endorsement flow."""
    session_data = _get_endorse_session(user)
    if session_data is None:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_endorse_session"

    idx = session_data["current_idx"]
    if idx > 0:
        session_data["current_idx"] = idx - 1
        user.bot_state_data = session_data
        await db.commit()

    return await _show_endorsement_policy(user, message, channel, db, session_data)


# ---------------------------------------------------------------------------
# Voice enrollment / verification handlers
# ---------------------------------------------------------------------------

async def _prompt_enrollment_language(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession,
) -> str:
    """Show language choice before starting voice enrollment."""
    settings = get_settings()
    total = settings.voice_enrollment_phrases_per_session
    user.bot_state = "choosing_voice_lang"
    user.bot_state_data = None
    await db.commit()
    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(user.locale, "voice_enroll_choose_lang", total=total),
        reply_markup=_voice_lang_keyboard(),
    ))
    return "voice_language_choice_prompted"


async def _handle_voice_lang_switch(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession,
) -> str:
    """Handle vlang_en / vlang_fa callback — switch language and proceed."""
    new_locale = (message.callback_data or "")[-2:]  # "en" or "fa"
    if new_locale not in ("en", "fa"):
        return "ignored"
    user.locale = new_locale

    state = user.bot_state

    if state == "choosing_voice_lang":
        # First-time language choice → start enrollment
        await db.commit()
        return await _start_voice_enrollment(user, message, channel, db)

    if state == "enrolling_voice":
        # Mid-enrollment language switch → reset enrollment, restart with new language phrases
        user.bot_state = None
        user.bot_state_data = None
        await db.commit()
        return await _start_voice_enrollment(user, message, channel, db)

    if state == "awaiting_voice":
        # During verification → pick new phrase in new language
        await db.commit()
        return await _start_voice_verification(user, message, channel, db)

    # Enrolled + active session — just update locale
    await db.commit()
    await _send_main_menu(user.locale, message.sender_ref, channel)
    return "locale_switched"


async def _start_voice_enrollment(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession,
) -> str:
    """Initialize voice enrollment and send first phrase prompt."""
    settings = get_settings()

    # Enforce 24-hour cooldown after enrollment block
    blocked_at_str = (user.bot_state_data or {}).get("enrollment_blocked_at")
    if blocked_at_str:
        blocked_at = datetime.fromisoformat(blocked_at_str)
        if datetime.now(UTC) - blocked_at < timedelta(hours=24):
            await channel.send_message(OutboundMessage(
                recipient_ref=message.sender_ref,
                text=_msg(user.locale, "voice_enroll_blocked"),
            ))
            return "voice_enrollment_cooldown"
        user.bot_state_data = None

    try:
        state = await start_enrollment(user)
        _, phrase_text = get_current_phrase(state, user.locale)
    except OSError:
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "voice_enroll_error"),
        ))
        return "voice_enrollment_error"

    user.bot_state = "enrolling_voice"
    user.bot_state_data = state
    await db.commit()

    total = settings.voice_enrollment_phrases_per_session
    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(
            user.locale, "voice_enroll_start",
            phrase=phrase_text,
            step=1,
            total=total,
        ),
        reply_markup=_voice_enroll_keyboard(user.locale),
    ))
    return "voice_enrollment_started"


async def _handle_enrollment_voice(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession,
) -> str:
    """Process a voice message during enrollment."""
    settings = get_settings()
    state = copy.deepcopy(user.bot_state_data or {})

    if not state.get("enrollment"):
        return await _start_voice_enrollment(user, message, channel, db)

    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(user.locale, "voice_processing"),
    ))

    try:
        status, updated_state = await process_enrollment_audio(
            user=user,
            state=state,
            channel=channel,
            file_id=message.voice_file_id or "",
            duration=message.voice_duration,
            session=db,
        )
    except OSError:
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "voice_enroll_error"),
        ))
        return "voice_enrollment_error"

    locale = user.locale

    if status == "enrollment_complete":
        await finalize_enrollment(user, updated_state, db)
        user.bot_state = None
        user.bot_state_data = None
        await db.commit()
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(locale, "voice_enroll_complete"),
        ))
        await _send_main_menu(locale, message.sender_ref, channel)
        return "voice_enrolled"

    if status == "phrase_accepted":
        _, phrase_text = get_current_phrase(updated_state, locale)
        user.bot_state_data = updated_state
        await db.commit()
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(
                locale, "voice_enroll_accepted",
                phrase=phrase_text,
                step=updated_state["step"] + 1,
                total=len(updated_state["phrase_ids"]),
            ),
            reply_markup=_voice_enroll_keyboard(locale),
        ))
        return "voice_phrase_accepted"

    if status == "phrase_retry":
        _, phrase_text = get_current_phrase(updated_state, locale)
        user.bot_state_data = updated_state
        await db.commit()
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(
                locale, "voice_enroll_retry",
                phrase=phrase_text,
                attempt=updated_state["attempt"] + 1,
                max_attempts=settings.voice_enrollment_attempts_per_phrase,
            ),
            reply_markup=_voice_enroll_keyboard(locale),
        ))
        return "voice_phrase_retry"

    if status == "phrase_replaced":
        _, phrase_text = get_current_phrase(updated_state, locale)
        user.bot_state_data = updated_state
        await db.commit()
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(locale, "voice_enroll_replaced", phrase=phrase_text),
            reply_markup=_voice_enroll_keyboard(locale),
        ))
        return "voice_phrase_replaced"

    if status == "enrollment_blocked":
        user.bot_state = None
        user.bot_state_data = {"enrollment_blocked_at": datetime.now(UTC).isoformat()}
        await db.commit()
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(locale, "voice_enroll_blocked"),
        ))
        return "voice_enrollment_blocked"

    # audio_error or service_error
    user.bot_state_data = updated_state
    await db.commit()
    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(locale, "voice_enroll_error"),
    ))
    return f"voice_{status}"


async def _start_voice_verification(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession,
) -> str:
    """Send a verification phrase prompt and set bot_state."""
    if not check_voice_rate_limit(str(user.id)):
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "voice_verify_rate_limited"),
        ))
        return "voice_rate_limited"

    phrase_id, phrase_text = pick_verification_phrase(user.locale)
    user.bot_state = "awaiting_voice"
    user.bot_state_data = {"verification": True, "phrase_id": phrase_id}
    await db.commit()

    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(user.locale, "voice_verify_prompt", phrase=phrase_text),
        reply_markup=_voice_verify_keyboard(user.locale),
    ))
    return "voice_verification_prompted"


async def _handle_verification_voice(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession,
) -> str:
    """Process a voice message during verification."""
    state = user.bot_state_data or {}
    phrase_id_raw = state.get("phrase_id")
    if phrase_id_raw is None:
        return await _start_voice_verification(user, message, channel, db)

    if not message.voice_file_id or not message.voice_file_id.strip():
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "voice_enroll_error"),
        ))
        return "voice_audio_error"

    if not check_voice_rate_limit(str(user.id)):
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "voice_verify_rate_limited"),
        ))
        return "voice_rate_limited"

    try:
        phrase_id = int(phrase_id_raw)
    except (TypeError, ValueError):
        return await _start_voice_verification(user, message, channel, db)

    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(user.locale, "voice_processing"),
    ))

    result, error_code = await verify_voice(
        user=user,
        channel=channel,
        file_id=message.voice_file_id.strip(),
        duration=message.voice_duration,
        phrase_id=phrase_id,
        session=db,
    )

    if result == "accept":
        user.bot_state = None
        user.bot_state_data = None
        await db.commit()
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "voice_verify_success"),
        ))
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "voice_verified"

    if result in ("audio_error", "service_error"):
        # User-facing validation: too short/long get specific messages; no technical code
        if error_code == "too_short":
            await channel.send_message(OutboundMessage(
                recipient_ref=message.sender_ref,
                text=_msg(user.locale, "voice_audio_too_short"),
            ))
            return "voice_audio_error"
        if error_code == "too_long":
            await channel.send_message(OutboundMessage(
                recipient_ref=message.sender_ref,
                text=_msg(user.locale, "voice_audio_too_long"),
            ))
            return "voice_audio_error"
        # Technical failure: show code for debugging/support
        code = error_code or "V003"
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "voice_technical_error", code=code),
        ))
        return f"voice_{result}"

    # reject — verification failed (wrong phrase or no match); show message then new phrase
    await channel.send_message(OutboundMessage(
        recipient_ref=message.sender_ref,
        text=_msg(user.locale, "voice_verify_failed"),
    ))
    return await _start_voice_verification(user, message, channel, db)


async def _handle_voice_message(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession,
) -> str:
    """Route voice message to enrollment or verification handler."""
    if user.bot_state == "enrolling_voice":
        return await _handle_enrollment_voice(user, message, channel, db)
    if user.bot_state == "awaiting_voice":
        return await _handle_verification_voice(user, message, channel, db)

    # Voice message when not in a voice state:
    # If not enrolled → start enrollment
    if not user.is_voice_enrolled:
        return await _start_voice_enrollment(user, message, channel, db)
    # If enrolled but session expired → start verification
    if not user.is_voice_session_active:
        return await _handle_verification_voice(user, message, channel, db)

    # Voice message when everything is fine — just ignore and show menu
    await _send_main_menu(user.locale, message.sender_ref, channel)
    return "voice_ignored"


async def _handle_cancel(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    user.bot_state = None
    user.bot_state_data = None
    await db.commit()
    await _send_main_menu(user.locale, message.sender_ref, channel)
    return "cancelled"


async def _route_callback(
    user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession
) -> str:
    data = message.callback_data or ""

    if data == "submit":
        return await _handle_submit_callback(user, message, channel, db)
    if data == "vote":
        return await _handle_vote_callback(user, message, channel, db)
    if data == "endorse":
        return await _handle_endorse_menu(user, message, channel, db)
    if data == "lang":
        return await _handle_lang_callback(user, message, channel, db)
    if data.startswith("vo:"):
        return await _handle_option_select(user, message, channel, db)
    if data == "vsk":
        return await _handle_skip_cluster(user, message, channel, db)
    if data == "vbk":
        return await _handle_vote_back(user, message, channel, db)
    if data == "vsub":
        return await _handle_vote_submit(user, message, channel, db)
    if data == "vchg":
        return await _handle_vote_change(user, message, channel, db)
    if data.startswith("e:"):
        return await _handle_endorse(user, message, channel, db)
    if data == "esk":
        return await _handle_endorse_skip(user, message, channel, db)
    if data == "ebk":
        return await _handle_endorse_back(user, message, channel, db)
    if data in {"cancel", "main"}:
        return await _handle_cancel(user, message, channel, db)

    await _send_main_menu(user.locale, message.sender_ref, channel)
    return "unknown_callback"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def route_message(
    *,
    session: AsyncSession,
    message: UnifiedMessage,
    channel: BaseChannel,
) -> str:
    if message.callback_data is not None:
        if message.callback_query_id:
            await channel.answer_callback(message.callback_query_id)

        user_result = await session.execute(
            select(User).where(User.messaging_account_ref == message.sender_ref)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            return "ignored"

        # Language switch callbacks — allowed at any stage (before/during enrollment, during verification)
        if message.callback_data and message.callback_data.startswith("vlang_"):
            return await _handle_voice_lang_switch(user, message, channel, session)

        # Voice gate for callbacks (same as for text): require enrollment then active session
        if not user.is_voice_enrolled:
            if user.bot_state == "choosing_voice_lang":
                # Waiting for language choice — re-prompt
                await channel.send_message(OutboundMessage(
                    recipient_ref=message.sender_ref,
                    text=_msg(user.locale, "voice_enroll_choose_lang",
                              total=get_settings().voice_enrollment_phrases_per_session),
                    reply_markup=_voice_lang_keyboard(),
                ))
                return "voice_language_choice_prompted"
            return await _prompt_enrollment_language(user, message, channel, session)
        if not user.is_voice_session_active:
            # Allow cancel/main to exit verification and show menu (e.g. to change language)
            if message.callback_data in {"cancel", "main"}:
                return await _handle_cancel(user, message, channel, session)
            return await _start_voice_verification(user, message, channel, session)

        return await _route_callback(user, message, channel, session)

    user_result = await session.execute(
        select(User).where(User.messaging_account_ref == message.sender_ref)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        from src.handlers.identity import resolve_linking_code

        ok, status, masked_email = await resolve_linking_code(
            session=session, code=message.text.strip(), account_ref=message.sender_ref,
        )
        if ok:
            linked_user_result = await session.execute(
                select(User).where(User.messaging_account_ref == message.sender_ref)
            )
            linked_user = linked_user_result.scalar_one_or_none()
            locale = linked_user.locale if linked_user else "en"
            template = _WELCOME.get(locale, _WELCOME["en"])
            text = template.format(email=masked_email or "")
            await channel.send_message(OutboundMessage(
                recipient_ref=message.sender_ref,
                text=text,
            ))
            # After linking, show language choice before enrollment
            if linked_user is not None:
                return await _prompt_enrollment_language(linked_user, message, channel, session)
            return "account_linked"
        if status == "user_already_linked":
            await channel.send_message(OutboundMessage(
                recipient_ref=message.sender_ref, text=USER_ALREADY_LINKED
            ))
            return status
        if status == "account_already_linked":
            await channel.send_message(OutboundMessage(
                recipient_ref=message.sender_ref, text=ACCOUNT_ALREADY_LINKED
            ))
            return status
        base_url = get_settings().app_public_base_url
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=REGISTER_HINT.format(url=base_url),
        ))
        return "registration_prompted"

    # --- Voice gate ---

    # 1. Voice message → route to voice handler
    if message.voice_file_id is not None:
        return await _handle_voice_message(user, message, channel, session)

    # 2. Not enrolled → guide through language choice → enrollment
    if not user.is_voice_enrolled:
        if user.bot_state == "choosing_voice_lang":
            # Waiting for language button press — re-prompt
            await channel.send_message(OutboundMessage(
                recipient_ref=message.sender_ref,
                text=_msg(user.locale, "voice_enroll_choose_lang",
                          total=get_settings().voice_enrollment_phrases_per_session),
                reply_markup=_voice_lang_keyboard(),
            ))
            return "voice_language_choice_prompted"
        if user.bot_state != "enrolling_voice":
            return await _prompt_enrollment_language(user, message, channel, session)
        # Text during enrollment — resend current phrase so they know what to read
        state = user.bot_state_data or {}
        _, phrase_text = get_current_phrase(state, user.locale)
        settings = get_settings()
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(
                user.locale, "voice_enroll_intro",
                phrase=phrase_text,
                step=state.get("step", 0) + 1,
                total=settings.voice_enrollment_phrases_per_session,
            ),
            reply_markup=_voice_enroll_keyboard(user.locale),
        ))
        return "voice_enrollment_nudge"

    # 3. Enrolled but session expired → prompt for verification
    if not user.is_voice_session_active:
        if user.bot_state == "awaiting_voice":
            # Allow text "cancel" / "انصراف" etc. to exit verification and show menu (e.g. change language)
            text_lower = (message.text or "").strip().lower()
            if text_lower in ("cancel", "main", "menu", "انصراف"):
                return await _handle_cancel(user, message, channel, session)
            # Otherwise nudge to send voice
            await channel.send_message(OutboundMessage(
                recipient_ref=message.sender_ref,
                text=_msg(user.locale, "voice_verify_nudge"),
            ))
            return "voice_verification_nudge"
        return await _start_voice_verification(user, message, channel, session)

    # --- End voice gate --- (session is active, proceed normally)

    # Extend voice session on meaningful actions
    if user.bot_state == "awaiting_submission":
        user.bot_state = None
        await session.commit()
        await handle_submission(message, user, channel, session)
        user.voice_verified_at = datetime.now(UTC)
        await session.commit()
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "submission_received"

    await _send_main_menu(user.locale, message.sender_ref, channel)
    return "menu_resent"

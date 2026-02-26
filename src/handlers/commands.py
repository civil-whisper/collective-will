from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.config import get_settings
from src.handlers.intake import handle_submission
from src.handlers.voting import cast_vote, record_endorsement
from src.models.cluster import Cluster
from src.models.policy_option import PolicyOption
from src.models.user import User
from src.models.vote import VotingCycle

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
        "no_active_cycle": "در حال حاضر رای‌گیری فعالی وجود ندارد.",
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
    },
    "en": {
        "submission_prompt": "📝 Please type your concern or policy proposal:",
        "menu_hint": "Please use the buttons below.",
        "no_active_cycle": "There is no active vote at this time.",
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
    },
}

_OPTION_LETTERS = "ABCDEFGHIJ"


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
            [{"text": "🗳️ رای دادن", "callback_data": "vote"}],
            [{"text": "🌐 Change language", "callback_data": "lang"}],
        ]
    },
    "en": {
        "inline_keyboard": [
            [{"text": "📝 Submit a concern", "callback_data": "submit"}],
            [{"text": "🗳️ Vote", "callback_data": "vote"}],
            [{"text": "🌐 تغییر زبان", "callback_data": "lang"}],
        ]
    },
}


def _main_menu_markup(locale: str) -> dict[str, list[list[dict[str, str]]]]:
    return _MAIN_MENU.get(locale, _MAIN_MENU["en"])


def _cancel_keyboard(locale: str) -> dict[str, list[list[dict[str, str]]]]:
    return {"inline_keyboard": [[{"text": _msg(locale, "cancel_btn"), "callback_data": "cancel"}]]}


# ---------------------------------------------------------------------------
# Endorsement keyboard builder
# ---------------------------------------------------------------------------

def _build_endorsement_keyboard(
    locale: str, cluster_count: int
) -> dict[str, list[list[dict[str, str]]]]:
    endorse_row: list[dict[str, str]] = []
    for i in range(cluster_count):
        endorse_row.append({
            "text": _msg(locale, "endorse_btn", n=i + 1),
            "callback_data": f"e:{i + 1}",
        })
    back_row = [{"text": _msg(locale, "back_btn"), "callback_data": "main"}]
    return {"inline_keyboard": [endorse_row, back_row]}


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
        return data
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
    """Show a summary of all selections before final submission."""
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
        reply_markup=_build_summary_keyboard(locale),
    ))
    return "summary_shown"


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
    analytics_url = f"{base_url}/{user.locale}/collective-concerns/top-policies"
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
    """Endorse a specific cluster."""
    parts = (message.callback_data or "").split(":")
    if len(parts) != 2:
        return "invalid_endorse"
    try:
        index = int(parts[1])
    except ValueError:
        return "invalid_endorse"

    cycle_result = await db.execute(
        select(VotingCycle)
        .where(VotingCycle.status == "active")
        .order_by(VotingCycle.started_at.desc())
    )
    active_cycle = cycle_result.scalars().first()
    if active_cycle is None or not active_cycle.cluster_ids:
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "no_active_cycle"

    if index < 1 or index > len(active_cycle.cluster_ids):
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "invalid_index"

    cluster_id = active_cycle.cluster_ids[index - 1]
    ok, status = await record_endorsement(session=db, user=user, cluster_id=cluster_id)
    if ok:
        await channel.send_message(OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "endorsement_recorded"),
        ))
    await _send_main_menu(user.locale, message.sender_ref, channel)
    return status


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
                reply_markup=_main_menu_markup(locale),
            ))
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

    if user.bot_state == "awaiting_submission":
        user.bot_state = None
        await session.commit()
        await handle_submission(message, user, channel, session)
        await _send_main_menu(user.locale, message.sender_ref, channel)
        return "submission_received"

    await _send_main_menu(user.locale, message.sender_ref, channel)
    return "menu_resent"

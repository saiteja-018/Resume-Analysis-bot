"""
CareerMatch AI — Telegram ATS Resume Analyzer Bot.

Entry point: handles all Telegram commands, document uploads,
text messages, greeting detection, rate limiting, and full report buttons.
"""

import os
import re
import logging
import tempfile
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    SUPPORTED_MIME_TYPES,
    MAX_FILE_SIZE_MB,
    MAX_RESUME_LENGTH,
    MAX_JD_LENGTH,
    validate_config,
)
from session_manager import sessions, SessionState, SessionMode
from document_parser import extract_text
from prompts import SYSTEM_PROMPT, build_user_message
from ai_engine import analyze
from response_formatter import format_response, get_page_footer, split_into_pages
from rate_limiter import rate_limiter
from utils import truncate_text

# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =============================================================================
# Greeting detection
# =============================================================================

GREETING_PATTERNS = re.compile(
    r"^\s*(hi|hello|hey|hola|howdy|yo|sup|hii+|heyy+|good\s*(morning|afternoon|evening|night)"
    r"|what'?s?\s*up|how\s*are\s*you|namaste|thanks?|thank\s*you|ok|okay|cool|nice"
    r"|great|awesome|bye|goodbye|see\s*ya|ciao)\s*[!?.,]*\s*$",
    re.IGNORECASE,
)

GREETING_RESPONSES = {
    "default": (
        "👋 Hey there! I'm CareerMatch AI — your resume analysis assistant.\n\n"
        "Here's what I can do for you:\n\n"
        "  📊  /analyze  — Match resume to a job description\n"
        "  📝  /review   — Get resume quality feedback\n"
        "  🔄  /compare  — Compare two resumes\n"
        "  📋  /jd       — Analyze a job description\n\n"
        "Send a command to get started! 🚀"
    ),
    "thanks": (
        "😊 You're welcome! Let me know if you need anything else.\n\n"
        "You can always start a new analysis with /analyze or /review."
    ),
    "bye": (
        "👋 Goodbye! Good luck with your job search! 🍀\n\n"
        "Come back anytime for another analysis."
    ),
}


def _get_greeting_response(text: str) -> str | None:
    """Return a greeting response if the text is a generic message, else None."""
    text = text.strip()
    if GREETING_PATTERNS.match(text):
        lower = text.lower().strip("!?., ")
        if any(w in lower for w in ("thank", "thanks")):
            return GREETING_RESPONSES["thanks"]
        elif any(w in lower for w in ("bye", "goodbye", "see ya", "ciao")):
            return GREETING_RESPONSES["bye"]
        return GREETING_RESPONSES["default"]
    return None


# =============================================================================
# Welcome & Help messages
# =============================================================================

WELCOME_MESSAGE = """🤖  Welcome to CareerMatch AI!

Your intelligent ATS Resume Analyzer,
Career Coach, and Resume Reviewer.

━━━━━━━━━━━━━━━━━━━━━━━━

  📊  /analyze  — Resume vs Job Description
  📝  /review   — Resume quality review
  🔄  /compare  — Compare two resumes
  📋  /jd       — Analyze a job description

━━━━━━━━━━━━━━━━━━━━━━━━

  📌  /status   — Check your session
  🔄  /reset    — Start fresh
  ❓  /help     — Full usage guide

Send a command to get started! 🚀"""


HELP_MESSAGE = """📖  HOW TO USE CAREERMATCH AI
━━━━━━━━━━━━━━━━━━━━━━━━

📊  RESUME vs JOB DESCRIPTION
  1.  Send /analyze
  2.  Upload your resume (PDF / DOCX)
  3.  Paste the job description
  4.  Get your ATS score + detailed report!

📝  RESUME REVIEW
  1.  Send /review
  2.  Upload your resume
  3.  Get quality feedback!

🔄  COMPARE TWO RESUMES
  1.  Send /compare
  2.  Upload Resume A
  3.  Upload Resume B
  4.  (Optional) Paste a JD for targeted comparison

📋  JOB DESCRIPTION ANALYSIS
  1.  Send /jd
  2.  Paste the job description
  3.  Get required skills, keywords & prep topics!

━━━━━━━━━━━━━━━━━━━━━━━━

💬  FOLLOW-UP QUESTIONS
  After any analysis, just type:
  • "Why is my score low?"
  • "What should I learn first?"
  • "Rewrite this bullet point"

📎  SUPPORTED FILES
  • PDF (.pdf)  •  Word (.docx)
  • Max size: 10 MB

⚡  RATE LIMIT
  • 5 analyses per hour per user

💡  TIPS
  • Use text-based resumes (not scanned images)
  • Paste complete job descriptions
  • Tap 'Full Report' for in-depth analysis"""


# =============================================================================
# Command Handlers
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME_MESSAGE)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_MESSAGE)


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    session.reset()
    session.mode = SessionMode.ANALYZE
    session.state = SessionState.WAITING_RESUME

    await update.message.reply_text(
        "📊  Resume vs Job Description Analysis\n\n"
        "📎  Please send me your resume file.\n"
        "     Supported: PDF, DOCX (max 10 MB)"
    )


async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    session.reset()
    session.mode = SessionMode.REVIEW
    session.state = SessionState.WAITING_RESUME

    await update.message.reply_text(
        "📝  Resume Quality Review\n\n"
        "📎  Please send me your resume file.\n"
        "     Supported: PDF, DOCX (max 10 MB)"
    )


async def cmd_compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    session.reset()
    session.mode = SessionMode.COMPARE
    session.state = SessionState.WAITING_RESUME

    await update.message.reply_text(
        "🔄  Resume Comparison\n\n"
        "📎  Please send me Resume A (PDF or DOCX)."
    )


async def cmd_jd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    session.reset()
    session.mode = SessionMode.JD_ONLY
    session.state = SessionState.WAITING_JD

    await update.message.reply_text(
        "📋  Job Description Analysis\n\n"
        "📝  Please paste the job description text."
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    session.full_reset()

    await update.message.reply_text(
        "🔄  Session cleared!\n\n"
        "Start a new analysis:\n"
        "  📊  /analyze   📝  /review\n"
        "  🔄  /compare   📋  /jd"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    remaining = rate_limiter.remaining(user_id)
    status = session.get_status_summary()

    await update.message.reply_text(
        f"📌  SESSION STATUS\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{status}\n\n"
        f"⚡  Rate limit: {remaining}/5 analyses remaining"
    )


# =============================================================================
# Document Handler
# =============================================================================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)

    if session.state not in (SessionState.WAITING_RESUME, SessionState.WAITING_RESUME_B):
        await update.message.reply_text(
            "🤔  I wasn't expecting a document right now.\n\n"
            "Start with a command:\n"
            "  📊 /analyze   📝 /review   🔄 /compare"
        )
        return

    document = update.message.document
    mime_type = document.mime_type or ""
    file_type = SUPPORTED_MIME_TYPES.get(mime_type)

    if not file_type:
        await update.message.reply_text(
            "❌  Unsupported file format.\n\n"
            "Please send a PDF (.pdf) or Word Document (.docx)."
        )
        return

    file_size_mb = (document.file_size or 0) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        await update.message.reply_text(
            f"❌  File too large ({file_size_mb:.1f} MB).\n"
            f"Maximum allowed: {MAX_FILE_SIZE_MB} MB."
        )
        return

    processing_msg = await update.message.reply_text("⏳  Processing your document...")

    temp_path = None
    try:
        file = await document.get_file()
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, f"resume.{file_type}")
        await file.download_to_drive(temp_path)

        text = extract_text(temp_path, file_type)
        text = truncate_text(text, MAX_RESUME_LENGTH)

        if session.state == SessionState.WAITING_RESUME:
            session.resume_a_text = text
            await _on_resume_a_received(update, context, session, processing_msg)
        elif session.state == SessionState.WAITING_RESUME_B:
            session.resume_b_text = text
            await _on_resume_b_received(update, context, session, processing_msg)

    except ValueError as e:
        await processing_msg.edit_text(f"❌  {str(e)}")
    except Exception as e:
        logger.error(f"Document processing error: {e}", exc_info=True)
        await processing_msg.edit_text(
            "❌  Failed to process the document.\n"
            "Make sure it's a valid, text-based PDF or DOCX."
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                os.rmdir(os.path.dirname(temp_path))
            except OSError:
                pass


async def _on_resume_a_received(update, context, session, processing_msg):
    chars = len(session.resume_a_text)

    if session.mode == SessionMode.ANALYZE:
        session.state = SessionState.WAITING_JD
        await processing_msg.edit_text(
            f"✅  Resume received!  ({chars} chars extracted)\n\n"
            "📝  Now paste the job description text."
        )

    elif session.mode == SessionMode.REVIEW:
        await processing_msg.edit_text(
            f"✅  Resume received!  ({chars} chars)\n\n"
            "⏳  Analyzing your resume..."
        )
        await _run_analysis(update, context, session)

    elif session.mode == SessionMode.COMPARE:
        session.state = SessionState.WAITING_RESUME_B
        await processing_msg.edit_text(
            f"✅  Resume A received!  ({chars} chars)\n\n"
            "📎  Now send me Resume B (PDF or DOCX)."
        )


async def _on_resume_b_received(update, context, session, processing_msg):
    chars = len(session.resume_b_text)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Add Job Description", callback_data="compare_add_jd"),
            InlineKeyboardButton("⚡ Compare Now", callback_data="compare_now"),
        ]
    ])

    session.state = SessionState.IDLE
    await processing_msg.edit_text(
        f"✅  Resume B received!  ({chars} chars)\n\n"
        "Add a job description for a targeted comparison,\n"
        "or compare directly?",
        reply_markup=keyboard,
    )


# =============================================================================
# Text Message Handler
# =============================================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    text = update.message.text.strip()

    if not text:
        return

    # ── Check for greetings / generic messages ──
    if session.state == SessionState.IDLE and not session.has_previous_analysis():
        greeting = _get_greeting_response(text)
        if greeting:
            await update.message.reply_text(greeting)
            return

    # ── Waiting for JD ──
    if session.state == SessionState.WAITING_JD:
        session.jd_text = truncate_text(text, MAX_JD_LENGTH)

        if session.mode == SessionMode.JD_ONLY:
            await update.message.reply_text("⏳  Analyzing the job description...")
            await _run_analysis(update, context, session)
        elif session.mode in (SessionMode.ANALYZE, SessionMode.COMPARE):
            await update.message.reply_text(
                f"✅  Job description received!  ({len(session.jd_text)} chars)\n\n"
                "⏳  Analyzing..."
            )
            await _run_analysis(update, context, session)
        return

    # ── Follow-up question on previous analysis ──
    if session.has_previous_analysis():
        # Check for greetings even with previous analysis
        greeting = _get_greeting_response(text)
        if greeting:
            await update.message.reply_text(greeting)
            return

        await update.message.reply_text("⏳  Thinking about your question...")
        await _run_follow_up(update, context, session, text)
        return

    # ── No context ──
    greeting = _get_greeting_response(text)
    if greeting:
        await update.message.reply_text(greeting)
        return

    await update.message.reply_text(
        "🤔  I need more context to help you.\n\n"
        "Start with a command:\n"
        "  📊 /analyze  — Resume vs JD\n"
        "  📝 /review   — Resume review\n"
        "  🔄 /compare  — Compare resumes\n"
        "  📋 /jd       — JD analysis\n\n"
        "Or send /help for the full guide."
    )


# =============================================================================
# Callback Query Handler
# =============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    session = sessions.get(user_id)
    data = query.data

    # ── Compare: add JD ──
    if data == "compare_add_jd":
        session.state = SessionState.WAITING_JD
        await query.edit_message_text(
            "📝  Please paste the job description text\n"
            "for a targeted comparison."
        )
        return

    # ── Compare: run now ──
    if data == "compare_now":
        await query.edit_message_text("⏳  Comparing resumes...")
        await _run_analysis_from_callback(query, context, session)
        return

    # ── Full Report button ──
    if data == "full_report":
        pages = context.user_data.get("full_report_pages", [])
        if pages:
            context.user_data["current_page"] = 0
            page_text = pages[0] + get_page_footer(1, len(pages))
            keyboard = _build_nav_keyboard(0, len(pages))
            await query.message.reply_text(text=page_text, reply_markup=keyboard)
        else:
            await query.message.reply_text("ℹ️  No additional details available.")
        return

    # ── New Analysis prompt ──
    if data == "new_analysis_prompt":
        await query.message.reply_text(
            "🚀  Start a new analysis:\n\n"
            "  📊  /analyze  — Resume vs Job Description\n"
            "  📝  /review   — Resume quality review\n"
            "  🔄  /compare  — Compare two resumes\n"
            "  📋  /jd       — Analyze a job description"
        )
        return

    # ── Page navigation ──
    if data.startswith("page_"):
        page_num = int(data.split("_")[1])
        pages = context.user_data.get("full_report_pages", [])
        if 0 <= page_num < len(pages):
            page_text = pages[page_num] + get_page_footer(page_num + 1, len(pages))
            keyboard = _build_nav_keyboard(page_num, len(pages))
            await query.edit_message_text(text=page_text, reply_markup=keyboard)
        return


# =============================================================================
# Analysis Execution
# =============================================================================

async def _check_rate_limit(update, user_id: int) -> bool:
    """Check rate limit. Returns True if allowed, False if blocked."""
    if not rate_limiter.is_allowed(user_id):
        retry = rate_limiter.retry_after(user_id)
        minutes = max(1, retry // 60)
        await update.effective_chat.send_message(
            f"⚠️  Rate limit reached!\n\n"
            f"You've used all 5 analyses this hour.\n"
            f"Try again in ~{minutes} minute(s).\n\n"
            f"💡  Meanwhile, you can ask follow-up questions\n"
            f"about your last analysis — those are free!"
        )
        return False
    return True


async def _run_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, session) -> None:
    user_id = update.effective_user.id

    # Rate limit check
    if not await _check_rate_limit(update, user_id):
        session.state = SessionState.IDLE
        return

    session.state = SessionState.ANALYZING
    rate_limiter.record(user_id)

    try:
        user_message = build_user_message(
            resume_a_text=session.resume_a_text,
            resume_b_text=session.resume_b_text,
            jd_text=session.jd_text,
        )

        result = await analyze(SYSTEM_PROMPT, user_message)
        session.last_analysis = result
        session.state = SessionState.IDLE

        formatted = format_response(result)
        await _send_result(update.effective_chat.id, formatted, context)

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        session.state = SessionState.IDLE
        await update.effective_chat.send_message(
            f"❌  Analysis failed. Please try again.\n\n"
            f"Error: {str(e)[:200]}"
        )


async def _run_analysis_from_callback(query, context, session) -> None:
    user_id = query.from_user.id

    if not rate_limiter.is_allowed(user_id):
        retry = rate_limiter.retry_after(user_id)
        minutes = max(1, retry // 60)
        await query.message.chat.send_message(
            f"⚠️  Rate limit reached! Try again in ~{minutes} minute(s)."
        )
        session.state = SessionState.IDLE
        return

    session.state = SessionState.ANALYZING
    rate_limiter.record(user_id)

    try:
        user_message = build_user_message(
            resume_a_text=session.resume_a_text,
            resume_b_text=session.resume_b_text,
            jd_text=session.jd_text,
        )

        result = await analyze(SYSTEM_PROMPT, user_message)
        session.last_analysis = result
        session.state = SessionState.IDLE

        formatted = format_response(result)
        await _send_result(query.message.chat_id, formatted, context)

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        session.state = SessionState.IDLE
        await query.message.chat.send_message(
            f"❌  Analysis failed. Please try again.\n\n"
            f"Error: {str(e)[:200]}"
        )


async def _run_follow_up(update, context, session, question: str) -> None:
    """Follow-up questions are free — no rate limit."""
    try:
        user_message = build_user_message(
            resume_a_text=session.resume_a_text,
            jd_text=session.jd_text,
            user_question=question,
            previous_analysis=session.last_analysis,
        )

        result = await analyze(SYSTEM_PROMPT, user_message)
        session.last_analysis = result

        formatted = format_response(result)
        await _send_result(update.effective_chat.id, formatted, context)

    except Exception as e:
        logger.error(f"Follow-up failed: {e}", exc_info=True)
        await update.effective_chat.send_message(
            f"❌  Couldn't process your question.\n\n"
            f"Error: {str(e)[:200]}"
        )


# =============================================================================
# Result Sending (Summary + Full Report button)
# =============================================================================

async def _send_result(chat_id: int, formatted: dict, context) -> None:
    """Send the summary card, then offer a Full Report button if detail pages exist."""
    summary = formatted.get("summary", "No results.")
    full_pages = formatted.get("full_report", [])

    # Store full report pages for later retrieval
    context.user_data["full_report_pages"] = full_pages

    # Split summary if it's too long
    summary_parts = split_into_pages(summary)

    for part in summary_parts:
        await context.bot.send_message(chat_id, part)

    # Show action buttons
    buttons = []

    if full_pages:
        buttons.append([
            InlineKeyboardButton("📋  Full Report", callback_data="full_report")
        ])

    buttons.append([
        InlineKeyboardButton("🔄  New Analysis", callback_data="new_analysis_prompt")
    ])

    remaining = "💬  Ask follow-up questions anytime — they're free!"

    await context.bot.send_message(
        chat_id,
        remaining,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def _build_nav_keyboard(current: int, total: int) -> InlineKeyboardMarkup | None:
    """Build navigation buttons for full report pages."""
    if total <= 1:
        return None

    nav_buttons = []
    if current > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️  Previous", callback_data=f"page_{current - 1}")
        )
    if current < total - 1:
        nav_buttons.append(
            InlineKeyboardButton("Next  ➡️", callback_data=f"page_{current + 1}")
        )

    return InlineKeyboardMarkup([nav_buttons])


# =============================================================================
# Bot Setup & Entry Point
# =============================================================================

async def set_bot_commands(app) -> None:
    commands = [
        BotCommand("start", "Welcome & quick start"),
        BotCommand("analyze", "Resume vs Job Description"),
        BotCommand("review", "Resume quality review"),
        BotCommand("compare", "Compare two resumes"),
        BotCommand("jd", "Analyze a job description"),
        BotCommand("status", "Check session & rate limit"),
        BotCommand("reset", "Clear session & start fresh"),
        BotCommand("help", "Usage guide"),
    ]
    await app.bot.set_my_commands(commands)


def main():
    validate_config()
    logger.info("Starting CareerMatch AI bot...")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .connection_pool_size(8)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("compare", cmd_compare))
    app.add_handler(CommandHandler("jd", cmd_jd))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("status", cmd_status))

    # Document handler (PDF/DOCX uploads)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Callback query handler (buttons)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Text handler (JD text, follow-ups, greetings) — must be LAST
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Post-init: set bot command menu
    app.post_init = set_bot_commands

    # Run with retries for unstable networks
    logger.info("Bot is running! Press Ctrl+C to stop.")
    app.run_polling(
        drop_pending_updates=True,
        bootstrap_retries=5,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()

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
    Application,
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
from utils import truncate_text, format_score_bar, score_emoji, priority_emoji, is_job_description_doc

# =============================================================================
# Logging (with token redaction for production safety)
# =============================================================================

class _TokenRedactionFilter(logging.Filter):
    """Redact Telegram bot tokens and complete API URLs from log messages to prevent secret leaks."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            changed = False
            if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN in msg:
                msg = msg.replace(TELEGRAM_BOT_TOKEN, "[REDACTED_BOT_TOKEN]")
                changed = True
            if "api.telegram.org" in msg:
                msg = re.sub(r"(https?://api\.telegram\.org/bot)[^/\s]+", r"\1[REDACTED_BOT_TOKEN]", msg)
                changed = True
            if changed:
                record.msg = msg
                record.args = ()
        except Exception:
            pass
        return True


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Apply token redaction to the root logger and all handlers
_redaction_filter = _TokenRedactionFilter()
logging.getLogger().addFilter(_redaction_filter)
for _h in logging.root.handlers:
    _h.addFilter(_redaction_filter)

# Suppress noisy httpx request logs (they contain token URLs)
logging.getLogger("httpx").setLevel(logging.WARNING)

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


SCORE_QUERY_PATTERNS = re.compile(
    r"^\s*(what('?s|\s+is)\s+)?(my\s+)?(ats\s+)?score\??\s*$",
    re.IGNORECASE,
)


def _is_score_query(text: str) -> bool:
    """Check if the user is simply requesting their current ATS score."""
    clean = text.strip().lower()
    return bool(
        SCORE_QUERY_PATTERNS.match(clean)
        or clean in ("score", "my score", "ats score", "current score", "show score")
    )


COMMON_VALID_WORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "have", "has", "had", "do", "does", "did",
    "can", "could", "should", "would", "will", "may", "might", "must",
    "i", "my", "me", "we", "our", "you", "your", "he", "she", "it", "they", "them",
    "what", "why", "how", "when", "where", "who", "which",
    "score", "resume", "cv", "job", "jd", "role", "work", "skills", "projects",
    "experience", "help", "review", "analyze", "compare", "improve", "learn",
    "python", "java", "sql", "aws", "react", "node", "docker", "tech", "dev", "data",
}


def _is_meaningful_text(text: str) -> bool:
    """
    Validate that user text is not random keyboard smash (e.g. 'wekhsekfdn skdfn skdj fskd').
    Always allows genuine text, technical acronyms, and long documents.
    """
    cleaned = text.strip()
    if len(cleaned) < 2:
        return False

    # Any text with 40+ chars and spaces is treated as genuine (e.g. pasted JD or resume)
    if len(cleaned) >= 40 and " " in cleaned:
        if not re.search(r'(.)\1{8,}', cleaned):
            return True

    words = [w.lower().strip(".,!?;:\"'()[]{}/*-_") for w in cleaned.split()]
    words = [w for w in words if w]
    if not words:
        return False

    # If any known valid word is present, it's meaningful
    if any(w in COMMON_VALID_WORDS for w in words):
        return True

    # Check for excessive single-character repetition
    if re.search(r'(.)\1{4,}', cleaned):
        return False

    # Check vowel ratio for text with >= 8 letters total
    vowels = set("aeiouy")
    total_letters = sum(len([c for c in w if c.isalpha()]) for w in words)
    total_vowels = sum(1 for c in cleaned.lower() if c in vowels)
    if total_letters >= 8 and (total_vowels / total_letters) < 0.15:
        return False

    return True


def _build_quick_score_card(session) -> str:
    """Build a quick, instant reminder card of the candidate's last ATS score."""
    ats = session.last_analysis.get("ats", {}) if session.last_analysis else {}
    overall = ats.get("overall_score", 0)
    interpretation = ats.get("interpretation", "")
    categories = ats.get("category_scores", {})

    lines = [
        "📊  YOUR LATEST ATS SCORE",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"  {score_emoji(overall)}  Overall Score:  {overall} / 100",
        f"  {format_score_bar(overall, bar_length=15)}",
        "",
    ]
    if interpretation:
        lines.append(f"  📝  {interpretation}")
        lines.append("")

    if categories:
        lines.append("📈  SCORE BREAKDOWN")
        lines.append("─" * 28)
        cat_config = [
            ("required_skill_match", "Required Skills"),
            ("keyword_match", "Keywords"),
            ("experience_project_relevance", "Experience/Projects"),
            ("education_certification_match", "Education/Certs"),
            ("ats_readability", "ATS Readability"),
            ("achievement_impact", "Impact & Outcomes"),
        ]
        for key, label in cat_config:
            score = categories.get(key, 0)
            lines.append(f"  • {label:<22} {score:>3}/100")
        lines.append("")

    lines.append("👇  Tap below to learn how to boost your score or prep for interviews!")
    return "\n".join(lines)



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

    if session.resume_count() >= 2:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔄 Compare All ({session.resume_count()}) Resumes", callback_data="compare_multi_now")],
            [InlineKeyboardButton("📝 Match with 1 JD", callback_data="auto_add_jd")],
            [InlineKeyboardButton("🔄 Clear & Start Fresh", callback_data="clear_resumes")],
        ])
        await update.message.reply_text(
            f"📂  You have {session.resume_count()} resumes loaded:\n"
            + "\n".join([f"  • 📄 {r.name}" for r in session.resumes]) + "\n\n"
            "Choose an option below, or send another resume to add more candidates:",
            reply_markup=keyboard,
        )
        return

    session.reset()
    session.mode = SessionMode.COMPARE
    session.state = SessionState.WAITING_RESUME

    await update.message.reply_text(
        "🔄  Multiple Resume Comparison\n\n"
        "📎  Send your resumes one by one (PDF or DOCX).\n\n"
        "💡  You can send 2, 3, 4, or more resumes to compare them side-by-side, "
        "or paste 1 Job Description to rank all candidates against that role!"
    )


async def cmd_jd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    session.reset()
    session.mode = SessionMode.JD_ONLY
    session.state = SessionState.WAITING_JD

    await update.message.reply_text(
        "📋  Job Description Analysis\n\n"
        "📝  Please send a JD file (DOCX or PDF), or paste the job description text."
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

    document = update.message.document
    mime_type = document.mime_type or ""
    file_type = SUPPORTED_MIME_TYPES.get(mime_type)

    # Fallback to extension check if mime_type is generic
    if not file_type and document.file_name:
        fname = document.file_name.lower()
        if fname.endswith(".pdf"):
            file_type = "pdf"
        elif fname.endswith(".docx"):
            file_type = "docx"

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
        temp_path = os.path.join(temp_dir, f"doc.{file_type}")
        await file.download_to_drive(temp_path)

        raw_text = extract_text(temp_path, file_type)
        file_display_name = document.file_name or f"Document.{file_type}"

        # ── Check if this document is a Job Description ──
        # It is a JD if:
        # 1. User explicitly requested JD analysis (/jd or JD_ONLY mode)
        # 2. Bot is waiting for a JD (WAITING_JD state)
        # 3. Filename or text patterns indicate it is a Job Description
        is_jd = (
            session.mode == SessionMode.JD_ONLY
            or session.state == SessionState.WAITING_JD
            or is_job_description_doc(file_display_name, raw_text)
        )

        # ══════════════════════════════════════════════════════════════════════
        # PATH A: Document is a Job Description (.docx or .pdf)
        # ══════════════════════════════════════════════════════════════════════
        if is_jd:
            session.jd_text = truncate_text(raw_text, MAX_JD_LENGTH)

            # Case A1: User is in JD_ONLY mode (e.g. /jd command)
            if session.mode == SessionMode.JD_ONLY:
                session.state = SessionState.ANALYZING
                await processing_msg.edit_text(
                    f"📋  Job description received from {file_display_name}!  ({len(session.jd_text)} chars)\n\n"
                    "⏳  Analyzing the job description..."
                )
                await _run_analysis(update, context, session)
                return

            # Case A2: User already has candidate resume(s) loaded!
            if session.has_resume():
                session.state = SessionState.ANALYZING
                total_resumes = session.resume_count()
                if total_resumes >= 2:
                    session.mode = SessionMode.COMPARE
                    names = ", ".join(r.name for r in session.resumes)
                    await processing_msg.edit_text(
                        f"📋  Job description received from {file_display_name}!  ({len(session.jd_text)} chars)\n\n"
                        f"👥  Ranking all {total_resumes} candidates ({names}) against this role...\n\n"
                        "⏳  Scoring match %, identifying skill gaps, and generating recommendations..."
                    )
                else:
                    session.mode = SessionMode.ANALYZE
                    r_name = session.resumes[0].name
                    await processing_msg.edit_text(
                        f"📋  Job description received from {file_display_name}!  ({len(session.jd_text)} chars)\n\n"
                        f"⏳  Matching resume '{r_name}' against this job description..."
                    )
                await _run_analysis(update, context, session)
                return

            # Case A3: No resumes loaded yet — user sent JD file first!
            session.mode = SessionMode.ANALYZE
            session.state = SessionState.WAITING_RESUME
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋  Analyze this JD Only", callback_data="auto_analyze_jd_now")],
                [InlineKeyboardButton("📎  Send Candidate Resume", callback_data="prompt_add_resume")],
                [InlineKeyboardButton("🔄  Clear", callback_data="clear_resumes")],
            ])
            await processing_msg.edit_text(
                f"📋  Job description received from {file_display_name}!  ({len(session.jd_text)} chars)\n\n"
                "Next steps:\n"
                "  • 📎 Send candidate resume file(s) (PDF or DOCX) to match against this job\n"
                "  • ⚡ Or tap below to analyze this Job Description directly:",
                reply_markup=keyboard,
            )
            return

        # ══════════════════════════════════════════════════════════════════════
        # PATH B: Document is a Candidate Resume (.docx or .pdf)
        # ══════════════════════════════════════════════════════════════════════
        text = truncate_text(raw_text, MAX_RESUME_LENGTH)
        session.add_resume(text, filename=file_display_name)
        total_resumes = session.resume_count()

        # Build formatted list of loaded candidates
        pool_lines = [f"  • 📄 #{r.index}: {r.name} ({len(r.text)} chars)" for r in session.resumes]
        pool_summary = "\n".join(pool_lines)

        # ── Case B1: First Resume Added ──
        if total_resumes == 1:
            # If a JD was already uploaded earlier, analyze immediately!
            if session.has_jd():
                session.mode = SessionMode.ANALYZE
                session.state = SessionState.ANALYZING
                await processing_msg.edit_text(
                    f"✅  Resume received: {file_display_name}  ({len(text)} chars)\n\n"
                    "⏳  Matching your resume against the uploaded job description..."
                )
                await _run_analysis(update, context, session)
                return

            if session.mode == SessionMode.REVIEW:
                session.state = SessionState.ANALYZING
                await processing_msg.edit_text(
                    f"✅  Resume received: {file_display_name}  ({len(text)} chars)\n\n"
                    "⏳  Reviewing resume quality & structure..."
                )
                await _run_analysis(update, context, session)
                return

            if session.mode == SessionMode.ANALYZE:
                session.state = SessionState.WAITING_JD
                await processing_msg.edit_text(
                    f"✅  Resume 1 received: {file_display_name}  ({len(text)} chars)\n\n"
                    "📝  Now please send or paste the Job Description (.docx, .pdf, or text) to match against."
                )
                return

            # Default / auto routing:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📝 Review Quality", callback_data="auto_review_now"),
                    InlineKeyboardButton("📊 Match with JD", callback_data="auto_add_jd"),
                ],
                [
                    InlineKeyboardButton("📎 Add 2nd Resume", callback_data="prompt_add_resume"),
                    InlineKeyboardButton("🔄 Clear", callback_data="clear_resumes"),
                ],
            ])

            await processing_msg.edit_text(
                f"✅  Resume 1 loaded: {file_display_name}  ({len(text)} chars)\n\n"
                f"📂  Candidate Pool (1 resume):\n"
                f"{pool_summary}\n\n"
                "Next steps:\n"
                "  • 📎 Send another resume to compare candidates\n"
                "  • 📝 Send or paste a Job Description (.docx, .pdf, or text) to match\n"
                "  • ⚡ Or choose an option below:",
                reply_markup=keyboard,
            )

        # ── Case B2: Multiple Resumes Added (2, 3, 4, 5...) ──
        else:
            buttons = []
            if session.has_jd():
                buttons.append([
                    InlineKeyboardButton(f"🏆 Rank All ({total_resumes}) vs JD", callback_data="compare_multi_now")
                ])
                buttons.append([
                    InlineKeyboardButton("📎 Add More", callback_data="prompt_add_resume"),
                    InlineKeyboardButton("🔄 Clear Pool", callback_data="clear_resumes"),
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(f"🔄 Compare All ({total_resumes}) Resumes", callback_data="compare_multi_now"),
                    InlineKeyboardButton("📝 Send / Paste JD", callback_data="auto_add_jd"),
                ])
                buttons.append([
                    InlineKeyboardButton("📎 Add More", callback_data="prompt_add_resume"),
                    InlineKeyboardButton("🔄 Clear Pool", callback_data="clear_resumes"),
                ])

            keyboard = InlineKeyboardMarkup(buttons)
            await processing_msg.edit_text(
                f"✅  Resume {total_resumes} loaded: {file_display_name}  ({len(text)} chars)\n\n"
                f"📂  Candidate Pool ({total_resumes} resumes loaded):\n"
                f"{pool_summary}\n\n"
                f"Ready to compare or match!\n"
                f"  • 📎 Send another resume to add more candidates\n"
                f"  • 📝 Send or paste a Job Description (.docx, .pdf, or text) to rank all {total_resumes} candidates\n"
                f"  • ⚡ Or tap below to compare now:",
                reply_markup=keyboard,
            )

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


# =============================================================================
# Text Message Handler
# =============================================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = sessions.get(user_id)
    text = update.message.text.strip()

    if not text:
        return

    # 1. Check for score inquiries ("score", "my score", "what is my score")
    if _is_score_query(text):
        if session.has_previous_analysis():
            score_card = _build_quick_score_card(session)
            buttons = [
                [
                    InlineKeyboardButton("💡  How to Boost Score?", callback_data="quick_improve"),
                    InlineKeyboardButton("🎯  Interview Questions", callback_data="quick_interview"),
                ],
                [
                    InlineKeyboardButton("🎓  Courses & Links", callback_data="show_courses"),
                    InlineKeyboardButton("🔄  New Analysis", callback_data="new_analysis_prompt"),
                ],
            ]
            await update.message.reply_text(score_card, reply_markup=InlineKeyboardMarkup(buttons))
            return
        else:
            await update.message.reply_text(
                "📊  No active ATS score found!\n\n"
                "To get an ATS score and match analysis:\n"
                "  📊  /analyze  — Compare resume with a Job Description\n"
                "  📝  /review   — Review resume quality & structure\n\n"
                "Or simply send your resume file (PDF/DOCX) or paste it to start!"
            )
            return

    # 2. Check for greetings / polite chat
    greeting = _get_greeting_response(text)
    if greeting:
        await update.message.reply_text(greeting)
        return

    # 3. Check for meaningless text / keyboard smash (e.g. 'wekhsekfdn skdfn skdj fskd')
    if not _is_meaningful_text(text):
        if session.has_previous_analysis():
            await update.message.reply_text(
                "⚠️  I didn't quite understand that message.\n\n"
                "Please ask a specific question about your resume, or choose an option below:",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("💡  How to Boost Score?", callback_data="quick_improve"),
                        InlineKeyboardButton("🎯  Interview Questions", callback_data="quick_interview"),
                    ],
                    [
                        InlineKeyboardButton("🎓  Courses & Links", callback_data="show_courses"),
                        InlineKeyboardButton("🔄  New Analysis", callback_data="new_analysis_prompt"),
                    ],
                ]),
            )
        else:
            await update.message.reply_text(
                "⚠️  I didn't quite understand that message.\n\n"
                "Start with one of the options below:\n"
                "  📊  /analyze  — Match resume to a job description\n"
                "  📝  /review   — Check resume quality\n"
                "  🔄  /compare  — Compare two resumes\n"
                "  📋  /jd       — Analyze a job description\n\n"
                "Or simply send a resume file (PDF or DOCX) to begin!"
            )
        return

    # 4. User ALREADY has resume(s) loaded and pastes text -> Treat as Job Description!
    if session.has_resume() and not session.has_previous_analysis():
        session.jd_text = truncate_text(text, MAX_JD_LENGTH)
        session.state = SessionState.ANALYZING
        resumes_count = session.resume_count()
        if resumes_count >= 2:
            session.mode = SessionMode.COMPARE
            names = ", ".join(r.name for r in session.resumes)
            await update.message.reply_text(
                f"✅  Job description received!  ({len(session.jd_text)} chars)\n\n"
                f"👥  Ranking all {resumes_count} candidates ({names}) against this job description...\n\n"
                "⏳  Evaluating match %, ranking candidates, and analyzing skill gaps..."
            )
        else:
            session.mode = SessionMode.ANALYZE
            await update.message.reply_text(
                f"✅  Job description received!  ({len(session.jd_text)} chars)\n\n"
                "⏳  Matching your resume against this job description..."
            )
        await _run_analysis(update, context, session)
        return

    # 5. Waiting for Job Description (e.g. after /analyze or /jd command)
    if session.state == SessionState.WAITING_JD:
        session.jd_text = truncate_text(text, MAX_JD_LENGTH)
        session.state = SessionState.ANALYZING
        if session.resume_count() >= 2:
            session.mode = SessionMode.COMPARE
            names = ", ".join(r.name for r in session.resumes)
            await update.message.reply_text(
                f"✅  Job description received!  ({len(session.jd_text)} chars)\n\n"
                f"👥  Ranking {session.resume_count()} candidates ({names}) against this job description...\n\n"
                "⏳  Evaluating match %, ranking candidates, and analyzing skill gaps..."
            )
            await _run_analysis(update, context, session)
        elif session.mode == SessionMode.JD_ONLY:
            await update.message.reply_text("⏳  Analyzing the job description...")
            await _run_analysis(update, context, session)
        else:
            await update.message.reply_text(
                f"✅  Job description received!  ({len(session.jd_text)} chars)\n\n"
                "⏳  Analyzing match with your resume..."
            )
            await _run_analysis(update, context, session)
        return

    # 6. Previous analysis exists:
    if session.has_previous_analysis():
        lower_text = text.lower()
        # If user pastes a new job description (> 120 chars with requirements/skills), analyze it!
        if len(text) > 120 and any(
            k in lower_text
            for k in (
                "requirement", "responsibilit", "qualification", "looking for",
                "skills", "experience", "developer", "engineer", "role", "job", "we need"
            )
        ):
            session.jd_text = truncate_text(text, MAX_JD_LENGTH)
            session.state = SessionState.ANALYZING
            resumes_count = session.resume_count()
            if resumes_count >= 2:
                session.mode = SessionMode.COMPARE
                names = ", ".join(r.name for r in session.resumes)
                await update.message.reply_text(
                    f"📋  New Job Description detected!  ({len(session.jd_text)} chars)\n\n"
                    f"👥  Re-ranking {resumes_count} candidates ({names}) against this new role...\n\n"
                    "⏳  Analyzing match..."
                )
            else:
                session.mode = SessionMode.ANALYZE
                await update.message.reply_text(
                    f"📋  New Job Description detected!  ({len(session.jd_text)} chars)\n\n"
                    "⏳  Matching your resume against this new role..."
                )
            await _run_analysis(update, context, session)
            return

        # Otherwise, treat as follow-up question
        await update.message.reply_text("⏳  Thinking about your question with career coach depth...")
        await _run_follow_up(update, context, session, text)
        return

    # 7. No resume loaded yet — Smart auto-detection of text type:
    lower_text = text.lower()
    is_jd = len(text) >= 80 and any(
        k in lower_text
        for k in (
            "requirement", "responsibilit", "qualification", "looking for",
            "we need", "must have", "years of experience", "job description", "salary"
        )
    )
    is_resume = len(text) >= 80 and any(
        k in lower_text
        for k in (
            "education", "experience", "work history", "curriculum vitae",
            "projects", "certifications", "skills:", "gpa", "b.tech", "b.e"
        )
    )

    if is_jd:
        session.jd_text = truncate_text(text, MAX_JD_LENGTH)
        session.mode = SessionMode.ANALYZE
        session.state = SessionState.WAITING_RESUME
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋  Analyze this JD Only", callback_data="auto_analyze_jd_now")]
        ])
        await update.message.reply_text(
            f"📋  Job description received!  ({len(session.jd_text)} chars)\n\n"
            "📎  Now send your resume file (PDF or DOCX) to match against this job,\n"
            "⚡  or tap below to analyze this job description directly.",
            reply_markup=keyboard,
        )
        return

    if is_resume:
        session.add_resume(truncate_text(text, MAX_RESUME_LENGTH), filename=f"Resume_{session.resume_count() + 1}")
        total = session.resume_count()
        if total >= 2:
            pool_lines = [f"  • 📄 #{r.index}: {r.name} ({len(r.text)} chars)" for r in session.resumes]
            pool_summary = "\n".join(pool_lines)
            buttons = [
                [
                    InlineKeyboardButton(f"🔄 Compare All ({total}) Resumes", callback_data="compare_multi_now"),
                    InlineKeyboardButton("📝 Paste JD", callback_data="auto_add_jd"),
                ],
                [
                    InlineKeyboardButton("📎 Add More", callback_data="prompt_add_resume"),
                    InlineKeyboardButton("🔄 Clear Pool", callback_data="clear_resumes"),
                ],
            ]
            await update.message.reply_text(
                f"✅  Resume {total} loaded from text!  ({len(text)} chars)\n\n"
                f"📂  Candidate Pool ({total} resumes loaded):\n"
                f"{pool_summary}\n\n"
                "Ready to compare or match!\n"
                "  • 📎 Send/paste another resume to add more\n"
                "  • 📝 Paste a Job Description to rank all candidates against 1 JD\n"
                "  • ⚡ Or tap below to compare now:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return
        else:
            session.mode = SessionMode.ANALYZE
            session.state = SessionState.WAITING_JD
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝  Review Resume Quality", callback_data="auto_review_now")],
                [InlineKeyboardButton("📎  Add 2nd Resume", callback_data="prompt_add_resume")],
            ])
            await update.message.reply_text(
                f"📄  Resume text received!  ({len(session.resumes[0].text)} chars)\n\n"
                "Next steps:\n"
                "  • 📝 Paste a Job Description to match against your resume\n"
                "  • 📎 Send/paste another resume to compare candidates\n"
                "  • ⚡ Or tap below to review this resume now:",
                reply_markup=keyboard,
            )
            return

    # 8. If text looks like a question or advice query, answer it directly!
    if any(q in lower_text for q in ("how", "what", "why", "can", "should", "tell", "explain", "tips", "advice", "help")):
        await update.message.reply_text("⏳  Thinking about your question with career coach depth...")
        await _run_follow_up(update, context, session, text)
        return

    # 9. Fallback guidance
    await update.message.reply_text(
        "🤔  I received your message!\n\n"
        "Here are the best ways to use CareerMatch AI:\n"
        "  📎  Upload your resume (PDF or DOCX)\n"
        "  📝  Paste a Job Description text to match\n"
        "  💬  Ask any career or interview question\n\n"
        "Or use a command:\n"
        "  📊 /analyze  — Resume vs JD\n"
        "  📝 /review   — Resume review\n"
        "  🔄 /compare  — Compare resumes\n"
        "  📋 /jd       — JD analysis"
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

    # ── Auto document quick actions ──
    if data == "auto_review_now":
        session.mode = SessionMode.REVIEW
        session.state = SessionState.ANALYZING
        await query.edit_message_text("⏳  Analyzing your resume...")
        await _run_analysis_from_callback(query, context, session)
        return

    if data == "auto_analyze_jd_now":
        session.mode = SessionMode.JD_ONLY
        session.state = SessionState.ANALYZING
        await query.edit_message_text("⏳  Analyzing the job description...")
        await _run_analysis_from_callback(query, context, session)
        return

    if data == "auto_add_jd":
        session.mode = SessionMode.ANALYZE
        session.state = SessionState.WAITING_JD
        await query.edit_message_text(
            "📝  Please send a Job Description file (.docx or .pdf),\n"
            "or paste the job description text to match against your resume."
        )
        return

    # ── Compare: add JD ──
    if data == "compare_add_jd":
        session.state = SessionState.WAITING_JD
        await query.edit_message_text(
            "📝  Please send a Job Description file (.docx or .pdf),\n"
            "or paste the job description text for a targeted comparison."
        )
        return

    # ── Compare: run now (2 or multiple resumes) ──
    if data in ("compare_now", "compare_multi_now"):
        total = session.resume_count()
        if total < 2:
            await query.message.reply_text("⚠️  Please provide at least 2 resumes to compare.")
            return
        session.mode = SessionMode.COMPARE
        session.state = SessionState.ANALYZING
        if session.has_jd():
            await query.edit_message_text(f"⏳  Ranking {total} candidates against the Job Description...")
        else:
            await query.edit_message_text(f"⏳  Comparing all {total} resumes across technical depth, caliber & impact...")
        await _run_analysis_from_callback(query, context, session)
        return

    # ── Add another resume prompt ──
    if data == "prompt_add_resume":
        next_num = session.resume_count() + 1
        await query.message.reply_text(
            f"📎  Please send resume #{next_num} (PDF or DOCX file), or paste candidate resume text."
        )
        return

    # ── Clear candidate pool ──
    if data == "clear_resumes":
        session.reset()
        await query.edit_message_text(
            "🗑️  Candidate pool and session cleared!\n\n"
            "Send a new resume file or use /start to begin fresh."
        )
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

    # ── Courses & Links button ──
    if data == "show_courses":
        if not session.last_analysis:
            await query.message.reply_text("ℹ️  No active analysis found. Start with /analyze.")
            return

        learning = session.last_analysis.get("learning_recommendations", [])
        if not learning:
            await query.message.reply_text("ℹ️  No specific course recommendations found for this analysis.")
            return

        lines = [
            "🎓  RECOMMENDED UPSKILLING COURSES & DIRECT LINKS",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for i, rec in enumerate(learning, 1):
            if isinstance(rec, dict):
                skill = rec.get("skill", "")
                priority = rec.get("priority", "medium")
                course_name = rec.get("course_name", "")
                platform = rec.get("platform", "")
                url = rec.get("url", "")
                reason = rec.get("reason", "")
                emoji = priority_emoji(priority)

                lines.append(f"  {i}. {emoji} {skill} [{priority.upper()}]")
                if reason:
                    lines.append(f"     📌 {reason}")
                if course_name:
                    plat_str = f" • {platform}" if platform else ""
                    lines.append(f"     🎓 Course: {course_name}{plat_str}")
                if url:
                    lines.append(f"     🔗 Link: {url}")
                lines.append("")
            else:
                lines.append(f"  {i}. • {rec}")
                lines.append("")

        lines.append("💡  Click the links above to enroll and bridge your skill gaps!")
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💡  How to Boost Score?", callback_data="quick_improve"),
                InlineKeyboardButton("🎯  Interview Questions", callback_data="quick_interview"),
            ],
            [InlineKeyboardButton("🔄  New Analysis", callback_data="new_analysis_prompt")],
        ])
        await query.message.reply_text("\n".join(lines), reply_markup=keyboard)
        return

    # ── Quick Score Improvement Tips ──
    if data == "quick_improve":
        if not session.last_analysis:
            await query.message.reply_text("ℹ️  No active analysis found. Start with /analyze.")
            return
        await query.message.reply_text("⏳  Analyzing your resume for the highest-impact score improvements...")
        await _run_follow_up(
            query.message.chat_id,
            context,
            session,
            "As a world-class technical recruiter and hiring manager, give me the 3 highest-leverage, specific adjustments I can make to my resume to maximize my ATS score and match this exact job. Include exact bullet point rewrites tailored to my background.",
        )
        return

    # ── Quick Interview Prep Questions ──
    if data == "quick_interview":
        if not session.last_analysis:
            await query.message.reply_text("ℹ️  No active analysis found. Start with /analyze.")
            return
        await query.message.reply_text("⏳  Formulating the toughest interview questions based on your skill gaps...")
        await _run_follow_up(
            query.message.chat_id,
            context,
            session,
            "Based on the gaps between my resume and this job description, what are the top 5 technical and behavioral interview questions the hiring manager will grill me on, and what key points should I highlight to prove competence?",
        )
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
            resumes=session.resumes,
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
            resumes=session.resumes,
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


async def _run_follow_up(target, context, session, question: str) -> None:
    """Follow-up questions with high-IQ career coach intelligence."""
    chat_id = target.effective_chat.id if hasattr(target, "effective_chat") else target

    try:
        user_message = build_user_message(
            resume_a_text=session.resume_a_text,
            jd_text=session.jd_text,
            user_question=question,
            previous_analysis=session.last_analysis,
        )

        result = await analyze(SYSTEM_PROMPT, user_message)
        # Preserve original session.last_analysis so full context is retained for subsequent questions!
        formatted = format_response(result)
        await _send_follow_up_result(chat_id, formatted, context)

    except Exception as e:
        logger.error(f"Follow-up failed: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id,
            f"❌  Couldn't process your question.\n\n"
            f"Error: {str(e)[:200]}"
        )


# =============================================================================
# Result Sending (Summary + Interactive Buttons)
# =============================================================================

async def _send_result(chat_id: int, formatted: dict, context) -> None:
    """Send the summary card, then offer interactive action buttons."""
    summary = formatted.get("summary", "No results.")
    full_pages = formatted.get("full_report", [])

    # Store full report pages for later retrieval
    context.user_data["full_report_pages"] = full_pages

    # Split summary if it's too long
    summary_parts = split_into_pages(summary)

    for part in summary_parts:
        await context.bot.send_message(chat_id, part)

    # Show rich action buttons
    buttons = []
    row1 = []
    if full_pages:
        row1.append(InlineKeyboardButton("📋  Full Report", callback_data="full_report"))
    row1.append(InlineKeyboardButton("🎓  Courses & Links", callback_data="show_courses"))
    buttons.append(row1)

    buttons.append([
        InlineKeyboardButton("💡  How to Boost Score?", callback_data="quick_improve"),
        InlineKeyboardButton("🎯  Interview Questions", callback_data="quick_interview"),
    ])

    buttons.append([
        InlineKeyboardButton("🔄  New Analysis", callback_data="new_analysis_prompt")
    ])

    guidance = "💬  Tap any button above or ask any follow-up question below!"

    await context.bot.send_message(
        chat_id,
        guidance,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _send_follow_up_result(chat_id: int, formatted: dict, context) -> None:
    """Send career coach insights with clean spacing and interactive follow-up buttons."""
    summary = formatted.get("summary", "No insights available.")
    pages = split_into_pages(summary)

    for page in pages:
        await context.bot.send_message(chat_id, page)

    buttons = [
        [
            InlineKeyboardButton("💡  How to Boost Score?", callback_data="quick_improve"),
            InlineKeyboardButton("🎯  Interview Questions", callback_data="quick_interview"),
        ],
        [
            InlineKeyboardButton("🎓  Courses & Links", callback_data="show_courses"),
            InlineKeyboardButton("🔄  New Analysis", callback_data="new_analysis_prompt"),
        ],
    ]

    await context.bot.send_message(
        chat_id,
        "💬  Ask another question anytime, or choose a next step above!",
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


# =============================================================================
# Render Web Service: Concurrent HTTP Health Server & Webhook Lifecycle
# =============================================================================

import asyncio
import signal
import time
from aiohttp import web
from telegram.error import TelegramError

_bot_start_time = time.time()


async def _handle_root(request: web.Request) -> web.Response:
    """GET / — Bot status page."""
    uptime = int(time.time() - _bot_start_time)
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    return web.Response(
        text=(
            f"CareerMatch AI Bot\n"
            f"Status: running\n"
            f"Uptime: {hours}h {minutes}m {seconds}s\n"
        ),
        content_type="text/plain",
    )


async def _handle_health(request: web.Request) -> web.Response:
    """GET /health — JSON health check for Render."""
    return web.json_response({"status": "ok"})


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Catch and log all errors occurring during update handling
    so errors are never silently swallowed.
    """
    err = context.error
    if isinstance(err, TelegramError):
        logger.error("Telegram API error encountered: %s", err, exc_info=err)
    else:
        logger.error("Unhandled exception during update processing: %s", err, exc_info=err)


async def main_async():
    validate_config()
    logger.info("Starting CareerMatch AI bot in webhook mode...")

    port = int(os.environ.get("PORT", "10000"))
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")

    if not render_url:
        logger.error("RENDER_EXTERNAL_URL is not set in the environment! Cannot configure webhook.")
        return

    webhook_path = "/webhook"
    webhook_url = f"{render_url.rstrip('/')}{webhook_path}"

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
    await set_bot_commands(app)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("compare", cmd_compare))
    app.add_handler(CommandHandler("jd", cmd_jd))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(global_error_handler)

    # Initialize Telegram app manually
    await app.initialize()
    await app.start()
    logger.info("Telegram bot initialized.")

    # HTTP Webhook Handler
    async def _handle_webhook(request: web.Request) -> web.Response:
        """POST /webhook — Receives updates from Telegram."""
        if webhook_secret:
            secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if secret_header != webhook_secret:
                logger.warning("Webhook authentication failed. Invalid secret token.")
                return web.Response(status=403, text="Forbidden")
        try:
            data = await request.json()
            update = Update.de_json(data, app.bot)
            await app.update_queue.put(update)
            return web.Response(status=200, text="OK")
        except Exception as e:
            logger.error("Error processing webhook request: %s", e, exc_info=True)
            return web.Response(status=500, text="Internal Server Error")

    # Start HTTP health server & webhook concurrently
    health_app = web.Application()
    health_app.router.add_get("/", _handle_root)
    health_app.router.add_get("/health", _handle_health)
    health_app.router.add_post(webhook_path, _handle_webhook)

    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("HTTP server: READY (Listening on 0.0.0.0:%d)", port)

    # Configure Telegram webhook
    try:
        await app.bot.set_webhook(
            url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        logger.info("Telegram webhook: READY")
        logger.info("Telegram webhook configured successfully. (URL: %s)", webhook_url)
    except Exception as e:
        logger.error("Failed to configure Telegram webhook: %s", e)

    logger.info("GLM configuration: READY")

    # Wait indefinitely until termination signal
    stop_signal = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler(*args):
        logger.info("Shutdown signal received: stopping application gracefully...")
        stop_signal.set()

    try:
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    except NotImplementedError:
        pass  # Windows fallback

    try:
        await stop_signal.wait()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")

    # Clean shutdown
    logger.info("Stopping HTTP server...")
    await runner.cleanup()
    logger.info("HTTP server stopped.")
    
    logger.info("Stopping Telegram application...")
    try:
        await app.bot.delete_webhook()
    except Exception:
        pass
    await app.stop()
    await app.shutdown()
    logger.info("Graceful shutdown complete.")


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()



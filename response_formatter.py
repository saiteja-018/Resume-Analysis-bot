"""
Response formatter for CareerMatch AI bot.
Converts structured AI JSON responses into beautifully formatted,
readable Telegram messages with proper spacing and structure.
"""

import logging
from config import TELEGRAM_MAX_MESSAGE_LENGTH
from utils import format_score_bar, score_emoji, priority_emoji, status_emoji

logger = logging.getLogger(__name__)


def format_response(analysis: dict) -> dict:
    """
    Convert an AI analysis JSON response into structured pages.

    Returns a dict with:
        "summary": str  — Always-shown first message (compact overview)
        "full_report": list[str] — Detailed pages unlocked by "Full Report" button
    """
    analysis_type = analysis.get("analysis_type", "unknown")

    if analysis_type == "resume_vs_jd":
        return _format_resume_vs_jd(analysis)
    elif analysis_type == "resume_comparison":
        return _format_comparison(analysis)
    elif analysis_type == "resume_only":
        return _format_resume_only(analysis)
    elif analysis_type == "jd_only":
        return _format_jd_only(analysis)
    elif analysis_type == "follow_up":
        return _format_follow_up(analysis)
    else:
        return _format_generic(analysis)


# ═══════════════════════════════════════════════════════════════════
# RESUME vs JD
# ═══════════════════════════════════════════════════════════════════

def _format_resume_vs_jd(analysis: dict) -> dict:
    summary = _build_overview_card(analysis)
    full_pages = []

    p2 = _build_detailed_skills(analysis)
    if p2:
        full_pages.append(p2)

    p3 = _build_detailed_issues(analysis)
    if p3:
        full_pages.append(p3)

    p4 = _build_detailed_projects(analysis)
    if p4:
        full_pages.append(p4)

    p5 = _build_detailed_learning(analysis)
    if p5:
        full_pages.append(p5)

    return {"summary": summary, "full_report": full_pages}


# ═══════════════════════════════════════════════════════════════════
# OVERVIEW CARD (shown immediately)
# ═══════════════════════════════════════════════════════════════════

def _build_overview_card(analysis: dict) -> str:
    lines = []
    ats = analysis.get("ats", {})
    overall = ats.get("overall_score", 0)
    interpretation = ats.get("interpretation", "")
    confidence = ats.get("confidence", "medium")
    summary_text = analysis.get("summary", "")

    # ── Header ──
    lines.append("╔══════════════════════════════╗")
    lines.append("║    📊  ATS ANALYSIS REPORT       ║")
    lines.append("╚══════════════════════════════╝")
    lines.append("")

    # ── Score Display ──
    lines.append(f"  {score_emoji(overall)}  Overall Score:  {overall} / 100")
    lines.append(f"  {format_score_bar(overall, bar_length=20)}")
    lines.append("")

    if interpretation:
        lines.append(f"  📝  {interpretation}")
        lines.append("")

    # ── Category Scores ──
    categories = ats.get("category_scores", {})
    if categories:
        lines.append("┌─────────────────────────────┐")
        lines.append("│  📈  SCORE BREAKDOWN              │")
        lines.append("├─────────────────────────────┤")

        cat_config = [
            ("required_skill_match",        "Required Skills    ", "35%"),
            ("keyword_match",               "Keyword Match      ", "20%"),
            ("experience_project_relevance", "Experience/Projects", "15%"),
            ("education_certification_match","Education/Certs    ", "10%"),
            ("ats_readability",             "ATS Readability    ", "10%"),
            ("achievement_impact",          "Achievement/Impact ", "10%"),
        ]

        for key, label, weight in cat_config:
            score = categories.get(key, 0)
            bar = format_score_bar(score, bar_length=8)
            lines.append(f"│  {score_emoji(score)} {label} {score:>3}/100 {bar} │")

        lines.append("└─────────────────────────────┘")
        lines.append("")

    # ── Quick Summary ──
    if summary_text:
        lines.append("💡  SUMMARY")
        lines.append("─" * 30)
        # Wrap summary into short lines
        for sentence in _split_sentences(summary_text):
            lines.append(f"  {sentence}")
        lines.append("")

    # ── Quick Strengths (top 3) ──
    strengths = analysis.get("strengths", [])
    if strengths:
        lines.append("💪  KEY STRENGTHS")
        lines.append("─" * 30)
        for s in strengths[:3]:
            lines.append(f"  ✅  {s}")
        lines.append("")

    # ── Top Missing Skills (top 3) ──
    skill_analysis = analysis.get("skill_analysis", {})
    missing = skill_analysis.get("missing", [])
    if missing:
        lines.append("⚠️  TOP GAPS")
        lines.append("─" * 30)
        for item in missing[:3]:
            skill = item.get("skill", str(item)) if isinstance(item, dict) else str(item)
            lines.append(f"  ❌  {skill}")
        lines.append("")

    # ── Confidence ──
    lines.append(f"🎯  Confidence: {confidence.upper()}")
    lines.append("⚠️  Estimated compatibility — not a hiring guarantee.")
    lines.append("")
    lines.append("👇  Tap 'Full Report' below for detailed analysis.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# DETAILED SKILLS PAGE
# ═══════════════════════════════════════════════════════════════════

def _build_detailed_skills(analysis: dict) -> str | None:
    skill_analysis = analysis.get("skill_analysis", {})
    keyword_analysis = analysis.get("keyword_analysis", {})

    if not skill_analysis and not keyword_analysis:
        return None

    lines = []
    lines.append("╔══════════════════════════════╗")
    lines.append("║    🎯  SKILLS ANALYSIS           ║")
    lines.append("╚══════════════════════════════╝")
    lines.append("")

    # ── Matched ──
    matched = skill_analysis.get("matched", [])
    if matched:
        lines.append("✅  MATCHED SKILLS")
        lines.append("─" * 30)
        for item in matched[:10]:
            if isinstance(item, dict):
                skill = item.get("skill", "")
                evidence = item.get("evidence", "")
                lines.append(f"  ✅  {skill}")
                if evidence:
                    lines.append(f"       ↳ {evidence}")
            else:
                lines.append(f"  ✅  {item}")
        lines.append("")

    # ── Partial ──
    partial = skill_analysis.get("partial", [])
    if partial:
        lines.append("⚠️  PARTIAL MATCHES")
        lines.append("─" * 30)
        for item in partial[:10]:
            if isinstance(item, dict):
                skill = item.get("skill", "")
                evidence = item.get("evidence", "")
                lines.append(f"  ⚠️  {skill}")
                if evidence:
                    lines.append(f"       ↳ {evidence}")
            else:
                lines.append(f"  ⚠️  {item}")
        lines.append("")

    # ── Missing ──
    missing = skill_analysis.get("missing", [])
    if missing:
        lines.append("❌  MISSING SKILLS")
        lines.append("─" * 30)
        for item in missing[:10]:
            skill = item.get("skill", str(item)) if isinstance(item, dict) else str(item)
            lines.append(f"  ❌  {skill}")
        lines.append("")

    # ── Unclear ──
    unclear = skill_analysis.get("unclear", [])
    if unclear:
        lines.append("❓  INSUFFICIENT EVIDENCE")
        lines.append("─" * 30)
        for item in unclear[:5]:
            skill = item.get("skill", str(item)) if isinstance(item, dict) else str(item)
            lines.append(f"  ❓  {skill}")
        lines.append("")

    # ── Keywords ──
    missing_kw = keyword_analysis.get("missing_keywords", [])
    matched_kw = keyword_analysis.get("matched_keywords", [])

    if matched_kw:
        lines.append("🔑  MATCHED KEYWORDS")
        lines.append("─" * 30)
        lines.append(f"  {', '.join(matched_kw[:15])}")
        lines.append("")

    if missing_kw:
        lines.append("🔍  MISSING KEYWORDS")
        lines.append("─" * 30)
        lines.append(f"  {', '.join(missing_kw[:15])}")
        lines.append("")

    warnings = keyword_analysis.get("warnings", [])
    if warnings:
        lines.append("⚠️  KEYWORD WARNINGS")
        lines.append("─" * 30)
        for w in warnings[:3]:
            lines.append(f"  • {w}")

    return "\n".join(lines) if len(lines) > 4 else None


# ═══════════════════════════════════════════════════════════════════
# DETAILED ISSUES PAGE
# ═══════════════════════════════════════════════════════════════════

def _build_detailed_issues(analysis: dict) -> str | None:
    strengths = analysis.get("strengths", [])
    issues = analysis.get("resume_issues", [])

    if not strengths and not issues:
        return None

    lines = []
    lines.append("╔══════════════════════════════╗")
    lines.append("║    🔍  RESUME REVIEW             ║")
    lines.append("╚══════════════════════════════╝")
    lines.append("")

    # ── Strengths ──
    if strengths:
        lines.append("💪  STRENGTHS")
        lines.append("─" * 30)
        for i, s in enumerate(strengths[:5], 1):
            lines.append(f"  {i}.  ✅  {s}")
        lines.append("")

    # ── Issues ──
    if issues:
        lines.append("🔍  ISSUES FOUND")
        lines.append("─" * 30)
        for i, issue in enumerate(issues[:5], 1):
            if isinstance(issue, dict):
                priority = issue.get("priority", "medium")
                problem = issue.get("problem", "")
                reason = issue.get("reason", "")
                recommendation = issue.get("recommendation", "")

                emoji = priority_emoji(priority)
                lines.append(f"  {i}.  {emoji}  [{priority.upper()}]  {problem}")
                lines.append("")
                if reason:
                    lines.append(f"       Why:  {reason}")
                if recommendation:
                    lines.append(f"       Fix:  {recommendation}")
                lines.append("")
            else:
                lines.append(f"  {i}.  {issue}")
                lines.append("")

    return "\n".join(lines) if len(lines) > 4 else None


# ═══════════════════════════════════════════════════════════════════
# DETAILED PROJECTS PAGE
# ═══════════════════════════════════════════════════════════════════

def _build_detailed_projects(analysis: dict) -> str | None:
    projects = analysis.get("projects_analysis", [])
    experience = analysis.get("experience_analysis", [])

    if not projects and not experience:
        return None

    lines = []
    lines.append("╔══════════════════════════════╗")
    lines.append("║    🛠️  PROJECTS & EXPERIENCE    ║")
    lines.append("╚══════════════════════════════╝")
    lines.append("")

    if projects:
        lines.append("📁  PROJECT ANALYSIS")
        lines.append("─" * 30)
        for proj in projects[:5]:
            if isinstance(proj, dict):
                name = proj.get("project", "Unnamed")
                relevance = proj.get("relevance", "unknown")
                p_strengths = proj.get("strengths", [])
                improvements = proj.get("improvements", [])

                rel_map = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}
                rel_label = rel_map.get(relevance.lower(), f"⚪ {relevance}")

                lines.append(f"  📌  {name}")
                lines.append(f"       Relevance: {rel_label}")

                for s in p_strengths[:3]:
                    lines.append(f"       ✅  {s}")
                for imp in improvements[:3]:
                    lines.append(f"       💡  {imp}")
                lines.append("")
            else:
                lines.append(f"  •  {proj}")
                lines.append("")

    if experience:
        lines.append("💼  EXPERIENCE ANALYSIS")
        lines.append("─" * 30)
        for exp in experience[:5]:
            if isinstance(exp, dict):
                for key, value in exp.items():
                    lines.append(f"  •  {key}: {value}")
            else:
                lines.append(f"  •  {exp}")
        lines.append("")

    return "\n".join(lines) if len(lines) > 4 else None


# ═══════════════════════════════════════════════════════════════════
# DETAILED LEARNING PAGE
# ═══════════════════════════════════════════════════════════════════

def _build_detailed_learning(analysis: dict) -> str | None:
    recommendations = analysis.get("learning_recommendations", [])
    action_plan = analysis.get("action_plan", [])

    if not recommendations and not action_plan:
        return None

    lines = []
    lines.append("╔══════════════════════════════╗")
    lines.append("║    📚  LEARNING & NEXT STEPS    ║")
    lines.append("╚══════════════════════════════╝")
    lines.append("")

    if recommendations:
        lines.append("📚  RECOMMENDED LEARNING")
        lines.append("─" * 30)
        for i, rec in enumerate(recommendations[:5], 1):
            if isinstance(rec, dict):
                skill = rec.get("skill", "")
                priority = rec.get("priority", "medium")
                reason = rec.get("reason", "")
                topics = rec.get("learning_topics", [])
                prereqs = rec.get("prerequisites", [])

                emoji = priority_emoji(priority)
                lines.append(f"  {i}.  {emoji}  {skill}  [{priority.upper()}]")
                lines.append("")
                if reason:
                    lines.append(f"       Why:  {reason}")
                if topics:
                    lines.append(f"       Learn:  {', '.join(topics[:5])}")
                if prereqs:
                    lines.append(f"       Prerequisites:  {', '.join(prereqs[:3])}")
                lines.append("")
            else:
                lines.append(f"  {i}.  {rec}")
                lines.append("")

    if action_plan:
        lines.append("🎯  ACTION PLAN")
        lines.append("─" * 30)
        for i, action in enumerate(action_plan[:5], 1):
            lines.append(f"  {i}.  ▶  {action}")
        lines.append("")

    lines.append("💬  Have questions? Just type them here!")

    return "\n".join(lines) if len(lines) > 4 else None


# ═══════════════════════════════════════════════════════════════════
# COMPARISON
# ═══════════════════════════════════════════════════════════════════

def _format_comparison(analysis: dict) -> dict:
    comp = analysis.get("comparison", {})
    summary_text = analysis.get("summary", "")

    # ── Summary Card ──
    lines = []
    winner = comp.get("overall_winner", "tie")
    score_a = comp.get("resume_a_score", 0)
    score_b = comp.get("resume_b_score", 0)

    lines.append("╔══════════════════════════════╗")
    lines.append("║    🔄  RESUME COMPARISON        ║")
    lines.append("╚══════════════════════════════╝")
    lines.append("")

    if summary_text:
        for sentence in _split_sentences(summary_text):
            lines.append(f"  {sentence}")
        lines.append("")

    # ── Winner ──
    lines.append("┌─────────────────────────────┐")
    if winner == "resume_a":
        lines.append("│  🏆  WINNER:  Resume A              │")
    elif winner == "resume_b":
        lines.append("│  🏆  WINNER:  Resume B              │")
    else:
        lines.append("│  🤝  RESULT:  Tie                    │")
    lines.append("├─────────────────────────────┤")
    lines.append(f"│  📄 Resume A:  {score_a:>3}/100  {format_score_bar(score_a, bar_length=10)}  │")
    lines.append(f"│  📄 Resume B:  {score_b:>3}/100  {format_score_bar(score_b, bar_length=10)}  │")
    lines.append("└─────────────────────────────┘")
    lines.append("")

    lines.append("👇  Tap 'Full Report' for detailed breakdown.")

    summary_card = "\n".join(lines)

    # ── Full report pages ──
    full_pages = []

    # Category comparison page
    categories = comp.get("category_comparison", [])
    if categories:
        cat_lines = []
        cat_lines.append("╔══════════════════════════════╗")
        cat_lines.append("║    📊  CATEGORY BREAKDOWN       ║")
        cat_lines.append("╚══════════════════════════════╝")
        cat_lines.append("")

        for cat in categories[:10]:
            if isinstance(cat, dict):
                name = cat.get("category", "")
                a_score = cat.get("resume_a_score", 0)
                b_score = cat.get("resume_b_score", 0)
                cat_winner = cat.get("winner", "tie")
                reason = cat.get("reason", "")

                icon = "🅰️" if cat_winner == "resume_a" else ("🅱️" if cat_winner == "resume_b" else "🤝")
                cat_lines.append(f"  {icon}  {name}")
                cat_lines.append(f"       A: {a_score}/100  vs  B: {b_score}/100")
                if reason:
                    cat_lines.append(f"       ↳ {reason}")
                cat_lines.append("")

        full_pages.append("\n".join(cat_lines))

    # Strengths & improvements page
    a_better = comp.get("resume_a_better_areas", [])
    b_better = comp.get("resume_b_better_areas", [])
    a_improve = comp.get("resume_a_improvements", [])
    b_improve = comp.get("resume_b_improvements", [])

    if a_better or b_better or a_improve or b_improve:
        detail_lines = []
        detail_lines.append("╔══════════════════════════════╗")
        detail_lines.append("║    💡  DETAILED COMPARISON      ║")
        detail_lines.append("╚══════════════════════════════╝")
        detail_lines.append("")

        if a_better:
            detail_lines.append("🅰️  RESUME A — STRONGER IN")
            detail_lines.append("─" * 30)
            for item in a_better[:5]:
                detail_lines.append(f"  ✅  {item}")
            detail_lines.append("")

        if b_better:
            detail_lines.append("🅱️  RESUME B — STRONGER IN")
            detail_lines.append("─" * 30)
            for item in b_better[:5]:
                detail_lines.append(f"  ✅  {item}")
            detail_lines.append("")

        if a_improve:
            detail_lines.append("🅰️  RESUME A — NEEDS IMPROVEMENT")
            detail_lines.append("─" * 30)
            for item in a_improve[:5]:
                detail_lines.append(f"  💡  {item}")
            detail_lines.append("")

        if b_improve:
            detail_lines.append("🅱️  RESUME B — NEEDS IMPROVEMENT")
            detail_lines.append("─" * 30)
            for item in b_improve[:5]:
                detail_lines.append(f"  💡  {item}")

        full_pages.append("\n".join(detail_lines))

    return {"summary": summary_card, "full_report": full_pages}


# ═══════════════════════════════════════════════════════════════════
# RESUME ONLY
# ═══════════════════════════════════════════════════════════════════

def _format_resume_only(analysis: dict) -> dict:
    summary = _build_overview_card(analysis)

    full_pages = []
    p2 = _build_detailed_issues(analysis)
    if p2:
        full_pages.append(p2)

    p3 = _build_detailed_projects(analysis)
    if p3:
        full_pages.append(p3)

    p4 = _build_detailed_learning(analysis)
    if p4:
        full_pages.append(p4)

    return {"summary": summary, "full_report": full_pages}


# ═══════════════════════════════════════════════════════════════════
# JD ONLY
# ═══════════════════════════════════════════════════════════════════

def _format_jd_only(analysis: dict) -> dict:
    lines = []
    summary_text = analysis.get("summary", "")

    lines.append("╔══════════════════════════════╗")
    lines.append("║    📋  JOB DESCRIPTION ANALYSIS  ║")
    lines.append("╚══════════════════════════════╝")
    lines.append("")

    if summary_text:
        for sentence in _split_sentences(summary_text):
            lines.append(f"  {sentence}")
        lines.append("")

    requirements = analysis.get("job_requirements", {})
    required = requirements.get("required", [])
    preferred = requirements.get("preferred", [])

    if required:
        lines.append("🔴  REQUIRED SKILLS")
        lines.append("─" * 30)
        for skill in required[:10]:
            lines.append(f"  •  {skill}")
        lines.append("")

    if preferred:
        lines.append("🟡  PREFERRED SKILLS")
        lines.append("─" * 30)
        for skill in preferred[:10]:
            lines.append(f"  •  {skill}")
        lines.append("")

    lines.append("👇  Tap 'Full Report' for interview topics & prep guide.")

    summary_card = "\n".join(lines)

    # Full report
    full_pages = []

    # Keywords + prep page
    detail_lines = []
    keywords = analysis.get("keyword_analysis", {})
    matched_kw = keywords.get("matched_keywords", [])
    if matched_kw:
        detail_lines.append("🔑  KEY TECHNICAL KEYWORDS")
        detail_lines.append("─" * 30)
        detail_lines.append(f"  {', '.join(matched_kw[:15])}")
        detail_lines.append("")

    learning = analysis.get("learning_recommendations", [])
    if learning:
        detail_lines.append("📚  PREPARATION TOPICS")
        detail_lines.append("─" * 30)
        for rec in learning[:5]:
            if isinstance(rec, dict):
                skill = rec.get("skill", "")
                topics = rec.get("learning_topics", [])
                detail_lines.append(f"  📌  {skill}")
                for topic in topics[:4]:
                    detail_lines.append(f"       •  {topic}")
                detail_lines.append("")
            else:
                detail_lines.append(f"  •  {rec}")

    action_plan = analysis.get("action_plan", [])
    if action_plan:
        detail_lines.append("🎯  INTERVIEW PREPARATION")
        detail_lines.append("─" * 30)
        for i, action in enumerate(action_plan[:5], 1):
            detail_lines.append(f"  {i}.  ▶  {action}")

    if detail_lines:
        full_pages.append("\n".join(detail_lines))

    return {"summary": summary_card, "full_report": full_pages}


# ═══════════════════════════════════════════════════════════════════
# FOLLOW-UP
# ═══════════════════════════════════════════════════════════════════

def _format_follow_up(analysis: dict) -> dict:
    answer = analysis.get("follow_up_answer", "")
    summary_text = analysis.get("summary", "")

    lines = []
    lines.append("╔══════════════════════════════╗")
    lines.append("║    💬  FOLLOW-UP ANSWER          ║")
    lines.append("╚══════════════════════════════╝")
    lines.append("")

    content = answer or summary_text or "No additional insights available."
    for sentence in _split_sentences(content):
        lines.append(f"  {sentence}")
    lines.append("")

    action_plan = analysis.get("action_plan", [])
    if action_plan:
        lines.append("🎯  SUGGESTED ACTIONS")
        lines.append("─" * 30)
        for i, action in enumerate(action_plan[:5], 1):
            lines.append(f"  {i}.  ▶  {action}")
        lines.append("")

    lines.append("💬  Feel free to ask more questions!")

    return {"summary": "\n".join(lines), "full_report": []}


# ═══════════════════════════════════════════════════════════════════
# GENERIC / FALLBACK
# ═══════════════════════════════════════════════════════════════════

def _format_generic(analysis: dict) -> dict:
    summary_text = analysis.get("summary", "")
    follow_up = analysis.get("follow_up_answer", "")

    lines = []
    lines.append("📋  ANALYSIS RESULT")
    lines.append("─" * 30)

    if summary_text:
        lines.append(summary_text)
    if follow_up:
        lines.append("")
        lines.append(follow_up)
    if not summary_text and not follow_up:
        lines.append("Analysis complete. No detailed results available.")

    return {"summary": "\n".join(lines), "full_report": []}


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _split_sentences(text: str, max_len: int = 70) -> list[str]:
    """Split text into readable lines, breaking at sentence boundaries."""
    if not text:
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:
        if len(current) + len(word) + 1 > max_len:
            if current:
                lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word

    if current:
        lines.append(current)

    return lines


def split_into_pages(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long text into pages that fit Telegram's message limit."""
    if len(text) <= max_length:
        return [text]

    pages = []
    current = ""

    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            if current:
                pages.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"

    if current.strip():
        pages.append(current.strip())

    return pages


def get_page_footer(current_page: int, total_pages: int) -> str:
    if total_pages <= 1:
        return ""
    return f"\n\n📄  Page {current_page} of {total_pages}"

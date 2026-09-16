"""
Response formatter for CareerMatch AI bot.

Telegram Output & Presentation Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Converts structured AI JSON responses into beautifully formatted,
readable Telegram messages optimized for mobile screens.

Design Rules:
  - Short paragraphs (2-3 sentences max)
  - One idea → one line / one bullet
  - Blank lines between every major section
  - Clear visual hierarchy: HEADER → SECTION → SUBSECTION
  - Emojis sparingly, never decorative
  - Important findings first, minor observations last
  - No dense text blocks
  - Optimized for Telegram's 4096 char limit
"""

import logging
from config import TELEGRAM_MAX_MESSAGE_LENGTH
from utils import format_score_bar, score_emoji, priority_emoji, status_emoji

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────

DIVIDER_MAIN = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
DIVIDER_SUB = "─" * 28
MAX_ITEMS_PER_LIST = 8
MAX_SUMMARY_SENTENCES = 3


# ═══════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def format_response(analysis: dict) -> dict:
    """
    Convert an AI analysis JSON response into structured pages.

    Returns a dict with:
        "summary": str  — Always-shown first message (compact overview)
        "full_report": list[str] — Detailed pages unlocked by "Full Report" button
    """
    analysis_type = analysis.get("analysis_type", "unknown")

    if analysis_type == "resume_vs_jd":
        result = _format_resume_vs_jd(analysis)
    elif analysis_type in ("multi_resume_jd", "resume_ranking_jd"):
        result = _format_multi_resume_jd(analysis)
    elif analysis_type in ("multi_resume_compare", "candidate_comparison"):
        result = _format_multi_resume_compare(analysis)
    elif analysis_type == "resume_comparison":
        if "candidate_rankings" in analysis:
            result = _format_multi_resume_compare(analysis)
        else:
            result = _format_comparison(analysis)
    elif analysis_type == "resume_only":
        result = _format_resume_only(analysis)
    elif analysis_type == "jd_only":
        result = _format_jd_only(analysis)
    elif analysis_type == "follow_up":
        result = _format_follow_up(analysis)
    else:
        if "candidate_rankings" in analysis:
            result = _format_multi_resume_jd(analysis)
        else:
            result = _format_generic(analysis)

    # Final presentation validation pass
    result["summary"] = _validate_presentation(result["summary"])
    result["full_report"] = [_validate_presentation(p) for p in result.get("full_report", [])]

    return result


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
# OVERVIEW CARD  (shown immediately)
# ═══════════════════════════════════════════════════════════════════

def _build_overview_card(analysis: dict) -> str:
    lines = []
    ats = analysis.get("ats", {})
    overall = ats.get("overall_score", 0)
    interpretation = ats.get("interpretation", "")
    confidence = ats.get("confidence", "medium")
    summary_text = analysis.get("summary", "")

    # ── Header ──
    lines.append("📊  ATS RESUME MATCH REPORT")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    # ── Score — prominent, isolated ──
    lines.append(f"{score_emoji(overall)}  Overall Match Score")
    lines.append("")
    lines.append(f"  {overall} / 100")
    lines.append(f"  {format_score_bar(overall, bar_length=15)}")
    lines.append("")

    if interpretation:
        # Break interpretation into short sentences
        for sentence in _split_sentences(interpretation, MAX_SUMMARY_SENTENCES):
            lines.append(f"  {sentence}")
        lines.append("")

    # ── Category Scores ──
    categories = ats.get("category_scores", {})
    if categories:
        lines.append("")
        lines.append("📈  SCORE BREAKDOWN")
        lines.append(DIVIDER_SUB)
        lines.append("")

        cat_config = [
            ("required_skill_match",         "Required Skills",     "35%"),
            ("keyword_match",                "Keyword Match",       "20%"),
            ("experience_project_relevance", "Experience/Projects", "15%"),
            ("education_certification_match", "Education/Certs",    "10%"),
            ("ats_readability",              "ATS Readability",     "10%"),
            ("achievement_impact",           "Impact & Outcomes",   "10%"),
        ]

        for key, label, weight in cat_config:
            score = categories.get(key, 0)
            bar = format_score_bar(score, bar_length=7)
            lines.append(f"  {score_emoji(score)}  {label:<18} {score:>3}/100  {bar}")

        lines.append("")

    # ── Executive Summary — short paragraphs only ──
    if summary_text:
        lines.append("")
        lines.append("💡  EXECUTIVE SUMMARY")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for sentence in _split_sentences(summary_text, MAX_SUMMARY_SENTENCES):
            lines.append(f"  {sentence}")
        lines.append("")

    # ── Key Skill Gaps — most important first ──
    skill_analysis = analysis.get("skill_analysis", {})
    missing = skill_analysis.get("missing", [])
    if missing:
        lines.append("")
        lines.append("⚠️  TOP SKILL GAPS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for item in missing[:4]:
            skill = item.get("skill", str(item)) if isinstance(item, dict) else str(item)
            lines.append(f"  ❌  {skill}")
        lines.append("")

    # ── Top Courses — prominent, with links ──
    learning = analysis.get("learning_recommendations", [])
    if learning:
        lines.append("")
        lines.append("🎓  RECOMMENDED COURSES")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for i, rec in enumerate(learning[:3], 1):
            if isinstance(rec, dict):
                _append_course_block(lines, i, rec)
            else:
                lines.append(f"  {i}. {rec}")
                lines.append("")

    # ── Footer ──
    lines.append("")
    lines.append(f"🎯  Confidence: {confidence.upper()}")
    lines.append("⚠️  Estimated ATS compatibility score")
    lines.append("")
    lines.append("👇  Tap buttons below for full breakdown")

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
    lines.append("🎯  DETAILED SKILLS BREAKDOWN")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    # ── Matched — one skill per line ──
    matched = skill_analysis.get("matched", [])
    if matched:
        lines.append("✅  MATCHED SKILLS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for item in matched[:MAX_ITEMS_PER_LIST]:
            if isinstance(item, dict):
                skill = item.get("skill", "")
                evidence = item.get("evidence", "")
                lines.append(f"  ✅  {skill}")
                if evidence:
                    lines.append(f"      ↳ {evidence}")
            else:
                lines.append(f"  ✅  {item}")
        lines.append("")

    # ── Partial — one skill per line ──
    partial = skill_analysis.get("partial", [])
    if partial:
        lines.append("")
        lines.append("⚠️  PARTIAL MATCHES")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for item in partial[:MAX_ITEMS_PER_LIST]:
            if isinstance(item, dict):
                skill = item.get("skill", "")
                evidence = item.get("evidence", "")
                lines.append(f"  ⚠️  {skill}")
                if evidence:
                    lines.append(f"      ↳ {evidence}")
            else:
                lines.append(f"  ⚠️  {item}")
        lines.append("")

    # ── Missing — one skill per line ──
    missing = skill_analysis.get("missing", [])
    if missing:
        lines.append("")
        lines.append("❌  MISSING SKILLS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for item in missing[:MAX_ITEMS_PER_LIST]:
            skill = item.get("skill", str(item)) if isinstance(item, dict) else str(item)
            lines.append(f"  ❌  {skill}")
        lines.append("")

    # ── Keywords — individual bullets, NOT comma-separated ──
    matched_kw = keyword_analysis.get("matched_keywords", [])
    missing_kw = keyword_analysis.get("missing_keywords", [])

    if matched_kw:
        lines.append("")
        lines.append("🔑  MATCHED KEYWORDS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for kw in matched_kw[:10]:
            lines.append(f"  ✅  {kw}")
        lines.append("")

    if missing_kw:
        lines.append("")
        lines.append("🔍  MISSING KEYWORDS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for kw in missing_kw[:10]:
            lines.append(f"  ❌  {kw}")
        lines.append("")

    return "\n".join(lines) if len(lines) > 3 else None


# ═══════════════════════════════════════════════════════════════════
# DETAILED ISSUES PAGE
# ═══════════════════════════════════════════════════════════════════

def _build_detailed_issues(analysis: dict) -> str | None:
    strengths = analysis.get("strengths", [])
    issues = analysis.get("resume_issues", [])

    if not strengths and not issues:
        return None

    lines = []
    lines.append("⚠️  RESUME ISSUES & FIXES")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    # ── Critical Issues First (importance ordering) ──
    if issues:
        # Sort by priority: critical > high > medium > low
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_issues = sorted(
            [i for i in issues if isinstance(i, dict)],
            key=lambda x: priority_order.get(x.get("priority", "medium").lower(), 2)
        )
        # Add non-dict issues at the end
        sorted_issues.extend([i for i in issues if not isinstance(i, dict)])

        lines.append("🔍  ISSUES DETECTED")
        lines.append(DIVIDER_SUB)
        lines.append("")

        for i, issue in enumerate(sorted_issues[:6], 1):
            if isinstance(issue, dict):
                priority = issue.get("priority", "medium")
                problem = issue.get("problem", "")
                reason = issue.get("reason", "")
                recommendation = issue.get("recommendation", "")

                emoji = priority_emoji(priority)

                lines.append(f"  {i}. {emoji}  [{priority.upper()}]")
                lines.append(f"     {problem}")
                lines.append("")

                if reason:
                    lines.append(f"     📌 Why: {reason}")

                if recommendation:
                    lines.append(f"     💡 Fix: {recommendation}")

                lines.append("")
            else:
                lines.append(f"  {i}. {issue}")
                lines.append("")

    # ── Strengths (secondary importance) ──
    if strengths:
        lines.append("")
        lines.append("💪  STRENGTHS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for i, s in enumerate(strengths[:5], 1):
            lines.append(f"  {i}. ✅  {s}")
        lines.append("")

    return "\n".join(lines) if len(lines) > 3 else None


# ═══════════════════════════════════════════════════════════════════
# DETAILED PROJECTS PAGE
# ═══════════════════════════════════════════════════════════════════

def _build_detailed_projects(analysis: dict) -> str | None:
    projects = analysis.get("projects_analysis", [])

    if not projects:
        return None

    lines = []
    lines.append("🛠️  PROJECTS & EXPERIENCE")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    lines.append("📁  PROJECT EVALUATION")
    lines.append(DIVIDER_SUB)
    lines.append("")

    for proj in projects[:5]:
        if isinstance(proj, dict):
            name = proj.get("project", "Project")
            relevance = proj.get("relevance", "unknown")
            p_strengths = proj.get("strengths", [])
            improvements = proj.get("improvements", [])

            rel_map = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}
            rel_label = rel_map.get(relevance.lower(), f"⚪ {relevance}")

            lines.append(f"  📌  {name}")
            lines.append(f"      Relevance: {rel_label}")
            lines.append("")

            for s in p_strengths[:2]:
                lines.append(f"      ✅  {s}")

            for imp in improvements[:2]:
                lines.append(f"      💡  {imp}")

            lines.append("")
        else:
            lines.append(f"  •  {proj}")
            lines.append("")

    return "\n".join(lines) if len(lines) > 3 else None


# ═══════════════════════════════════════════════════════════════════
# DETAILED LEARNING PAGE  (Courses & Direct Links)
# ═══════════════════════════════════════════════════════════════════

def _build_detailed_learning(analysis: dict) -> str | None:
    recommendations = analysis.get("learning_recommendations", [])
    action_plan = analysis.get("action_plan", [])

    if not recommendations and not action_plan:
        return None

    lines = []
    lines.append("📚  UPSKILLING & COURSES")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    if recommendations:
        lines.append("🎓  CURATED LEARNING PATH")
        lines.append(DIVIDER_SUB)
        lines.append("")

        for i, rec in enumerate(recommendations[:5], 1):
            if isinstance(rec, dict):
                _append_course_block(lines, i, rec, show_candidate=True)
            else:
                lines.append(f"  {i}. {rec}")
                lines.append("")

    if action_plan:
        lines.append("")
        lines.append("🎯  ACTION PLAN")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for i, action in enumerate(action_plan[:5], 1):
            lines.append(f"  {i}. ▶  {action}")
        lines.append("")

    return "\n".join(lines) if len(lines) > 3 else None


# ═══════════════════════════════════════════════════════════════════
# MULTI-RESUME BATCH RANKING  (vs JD)
# ═══════════════════════════════════════════════════════════════════

def _format_multi_resume_jd(analysis: dict) -> dict:
    lines = []
    summary_text = analysis.get("summary", "")
    winner = analysis.get("winner", {})
    rankings = analysis.get("candidate_rankings", [])

    # ── Header ──
    lines.append("🏆  CANDIDATE LEADERBOARD")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    # ── Winner — prominent, isolated ──
    if winner:
        w_name = winner.get("candidate_name", "Top Candidate")
        w_score = winner.get("score", 0)
        w_reason = winner.get("why_selected", "")

        lines.append(f"👑  TOP PICK:  {w_name}")
        lines.append("")
        lines.append(f"  Match Score: {w_score} / 100")
        lines.append(f"  {score_emoji(w_score)}  {format_score_bar(w_score, bar_length=12)}")

        if w_reason:
            lines.append("")
            lines.append(f"  ↳ {w_reason}")

        lines.append("")

    # ── Summary ──
    if summary_text:
        lines.append("")
        lines.append("💡  EXECUTIVE SUMMARY")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for sentence in _split_sentences(summary_text, MAX_SUMMARY_SENTENCES):
            lines.append(f"  {sentence}")
        lines.append("")

    # ── Rankings — one block per candidate ──
    if rankings:
        lines.append("")
        lines.append("📊  CANDIDATE RANKINGS")
        lines.append(DIVIDER_SUB)
        lines.append("")

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]
        for i, cand in enumerate(rankings):
            rank = cand.get("rank", i + 1)
            name = cand.get("candidate_name", f"Candidate {rank}")
            score = cand.get("score", 0)
            level = cand.get("match_level", "")
            strengths = cand.get("key_strengths", [])
            missing = cand.get("missing_skills", [])
            verdict = cand.get("verdict", "")

            badge = medals[i] if i < len(medals) else f"#{rank}"

            lines.append(f"  {badge}  #{rank} • {name}")
            lines.append(f"     Score: {score} / 100  {score_emoji(score)}")
            lines.append(f"     {format_score_bar(score, bar_length=8)}")

            if level:
                lines.append(f"     Level: {level}")

            if strengths:
                lines.append("")
                for s in strengths[:3]:
                    lines.append(f"     ✅  {s}")

            if missing:
                lines.append("")
                for m in missing[:3]:
                    lines.append(f"     ❌  {m}")

            if verdict:
                lines.append("")
                lines.append(f"     🎯  {verdict}")

            lines.append("")

    # ── Courses ──
    learning = analysis.get("learning_recommendations", [])
    if learning:
        lines.append("")
        lines.append("🎓  TARGETED UPSKILLING COURSES")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for i, rec in enumerate(learning[:4], 1):
            if isinstance(rec, dict):
                _append_course_block(lines, i, rec, show_candidate=True)

    # ── Footer ──
    lines.append("")
    lines.append("👇  Ask a follow-up question or tap a button below")

    return {"summary": "\n".join(lines), "full_report": []}


# ═══════════════════════════════════════════════════════════════════
# MULTI-RESUME COMPARISON  (No JD)
# ═══════════════════════════════════════════════════════════════════

def _format_multi_resume_compare(analysis: dict) -> dict:
    lines = []
    summary_text = analysis.get("summary", "")
    winner = analysis.get("winner", {})
    rankings = analysis.get("candidate_rankings", [])

    # ── Header ──
    lines.append("🔄  RESUME COMPARISON LEADERBOARD")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    # ── Winner ──
    if winner:
        w_name = winner.get("candidate_name", "Strongest Candidate")
        w_score = winner.get("score", 0)
        w_reason = winner.get("why_selected", "")

        lines.append(f"🏆  STRONGEST:  {w_name}")
        lines.append("")
        lines.append(f"  Quality Score: {w_score} / 100")
        lines.append(f"  {score_emoji(w_score)}  {format_score_bar(w_score, bar_length=12)}")

        if w_reason:
            lines.append("")
            lines.append(f"  ↳ {w_reason}")

        lines.append("")

    # ── Summary ──
    if summary_text:
        lines.append("")
        lines.append("💡  EXECUTIVE SUMMARY")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for sentence in _split_sentences(summary_text, MAX_SUMMARY_SENTENCES):
            lines.append(f"  {sentence}")
        lines.append("")

    # ── Rankings ──
    if rankings:
        lines.append("")
        lines.append("📊  CANDIDATE RANKINGS")
        lines.append(DIVIDER_SUB)
        lines.append("")

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]
        for i, cand in enumerate(rankings):
            rank = cand.get("rank", i + 1)
            name = cand.get("candidate_name", f"Candidate {rank}")
            score = cand.get("score", 0)
            strengths = cand.get("key_strengths", [])
            improvements = cand.get("improvement_areas", [])
            verdict = cand.get("verdict", "")

            badge = medals[i] if i < len(medals) else f"#{rank}"

            lines.append(f"  {badge}  #{rank} • {name}")
            lines.append(f"     Score: {score} / 100  {score_emoji(score)}")
            lines.append(f"     {format_score_bar(score, bar_length=8)}")

            if strengths:
                lines.append("")
                for s in strengths[:3]:
                    lines.append(f"     ✅  {s}")

            if improvements:
                lines.append("")
                for imp in improvements[:3]:
                    lines.append(f"     ⚠️  {imp}")

            if verdict:
                lines.append("")
                lines.append(f"     🎯  {verdict}")

            lines.append("")

    # ── Courses ──
    learning = analysis.get("learning_recommendations", [])
    if learning:
        lines.append("")
        lines.append("🎓  RECOMMENDED COURSES")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for i, rec in enumerate(learning[:3], 1):
            if isinstance(rec, dict):
                _append_course_block(lines, i, rec, show_candidate=True)

    # ── Footer ──
    lines.append("")
    lines.append("👇  Ask a follow-up question or tap a button below")

    return {"summary": "\n".join(lines), "full_report": []}


# ═══════════════════════════════════════════════════════════════════
# COMPARISON  (2 Resumes Legacy)
# ═══════════════════════════════════════════════════════════════════

def _format_comparison(analysis: dict) -> dict:
    comp = analysis.get("comparison", {})
    summary_text = analysis.get("summary", "")

    # ── Summary Card ──
    lines = []
    winner = comp.get("overall_winner", "tie")
    score_a = comp.get("resume_a_score", 0)
    score_b = comp.get("resume_b_score", 0)

    lines.append("🔄  CANDIDATE COMPARISON REPORT")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    # ── Winner — prominent ──
    if winner == "resume_a":
        lines.append("🏆  OVERALL WINNER:  Resume A")
    elif winner == "resume_b":
        lines.append("🏆  OVERALL WINNER:  Resume B")
    else:
        lines.append("🤝  OVERALL RESULT:  Tie")

    lines.append("")

    # ── Scores — separated, not jammed ──
    lines.append("📄  Resume A")
    lines.append(f"  {score_a} / 100  {format_score_bar(score_a, bar_length=10)}")
    lines.append("")
    lines.append("📄  Resume B")
    lines.append(f"  {score_b} / 100  {format_score_bar(score_b, bar_length=10)}")
    lines.append("")

    # ── Summary ──
    if summary_text:
        lines.append("")
        lines.append("💡  EXECUTIVE SUMMARY")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for sentence in _split_sentences(summary_text, MAX_SUMMARY_SENTENCES):
            lines.append(f"  {sentence}")
        lines.append("")

    # ── Courses ──
    learning = analysis.get("learning_recommendations", [])
    if learning:
        lines.append("")
        lines.append("🎓  RECOMMENDED COURSES")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for i, rec in enumerate(learning[:2], 1):
            if isinstance(rec, dict):
                _append_course_block(lines, i, rec, show_candidate=True)

    # ── Footer ──
    lines.append("")
    lines.append("👇  Tap 'Full Report' for detailed breakdown")

    summary_card = "\n".join(lines)

    # ── Full report pages ──
    full_pages = []

    # Category comparison page
    categories = comp.get("category_comparison", [])
    if categories:
        cat_lines = []
        cat_lines.append("📊  CATEGORY COMPARISON")
        cat_lines.append(DIVIDER_MAIN)
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
                cat_lines.append(f"      A: {a_score}/100  vs  B: {b_score}/100")

                if reason:
                    cat_lines.append(f"      ↳ {reason}")

                cat_lines.append("")

        full_pages.append("\n".join(cat_lines))

    # Strengths & improvements page
    a_better = comp.get("resume_a_better_areas", [])
    b_better = comp.get("resume_b_better_areas", [])
    a_improve = comp.get("resume_a_improvements", [])
    b_improve = comp.get("resume_b_improvements", [])

    if a_better or b_better or a_improve or b_improve:
        detail_lines = []
        detail_lines.append("💡  STRENGTHS & IMPROVEMENTS")
        detail_lines.append(DIVIDER_MAIN)
        detail_lines.append("")

        if a_better:
            detail_lines.append("🅰️  RESUME A — STRONGER IN")
            detail_lines.append(DIVIDER_SUB)
            detail_lines.append("")
            for item in a_better[:4]:
                detail_lines.append(f"  ✅  {item}")
            detail_lines.append("")

        if b_better:
            detail_lines.append("")
            detail_lines.append("🅱️  RESUME B — STRONGER IN")
            detail_lines.append(DIVIDER_SUB)
            detail_lines.append("")
            for item in b_better[:4]:
                detail_lines.append(f"  ✅  {item}")
            detail_lines.append("")

        if a_improve:
            detail_lines.append("")
            detail_lines.append("🅰️  RESUME A — NEEDS IMPROVEMENT")
            detail_lines.append(DIVIDER_SUB)
            detail_lines.append("")
            for item in a_improve[:4]:
                detail_lines.append(f"  💡  {item}")
            detail_lines.append("")

        if b_improve:
            detail_lines.append("")
            detail_lines.append("🅱️  RESUME B — NEEDS IMPROVEMENT")
            detail_lines.append(DIVIDER_SUB)
            detail_lines.append("")
            for item in b_improve[:4]:
                detail_lines.append(f"  💡  {item}")
            detail_lines.append("")

        full_pages.append("\n".join(detail_lines))

    # Upskilling page
    learn_page = _build_detailed_learning(analysis)
    if learn_page:
        full_pages.append(learn_page)

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

    lines.append("📋  JOB DESCRIPTION ANALYSIS")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    if summary_text:
        for sentence in _split_sentences(summary_text, MAX_SUMMARY_SENTENCES):
            lines.append(f"  {sentence}")
        lines.append("")

    requirements = analysis.get("job_requirements", {})
    required = requirements.get("required", [])
    preferred = requirements.get("preferred", [])

    if required:
        lines.append("")
        lines.append("🔴  REQUIRED SKILLS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for skill in required[:10]:
            lines.append(f"  •  {skill}")
        lines.append("")

    if preferred:
        lines.append("")
        lines.append("🟡  PREFERRED SKILLS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for skill in preferred[:10]:
            lines.append(f"  •  {skill}")
        lines.append("")

    lines.append("")
    lines.append("👇  Tap 'Full Report' for keywords & prep courses")

    summary_card = "\n".join(lines)

    full_pages = []
    learn_page = _build_detailed_learning(analysis)
    if learn_page:
        full_pages.append(learn_page)

    return {"summary": summary_card, "full_report": full_pages}


# ═══════════════════════════════════════════════════════════════════
# FOLLOW-UP  (Career Coach Answer)
# ═══════════════════════════════════════════════════════════════════

def _format_follow_up(analysis: dict) -> dict:
    answer = analysis.get("follow_up_answer", "")
    summary_text = analysis.get("summary", "")

    lines = []
    lines.append("💡  CAREER COACH INSIGHTS")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    content = answer or summary_text or "No additional insights available."

    # Break into short paragraphs
    for sentence in _split_sentences(content):
        lines.append(f"  {sentence}")
    lines.append("")

    # ── Action Steps ──
    action_plan = analysis.get("action_plan", [])
    if action_plan:
        lines.append("")
        lines.append("🎯  ACTION STEPS")
        lines.append(DIVIDER_SUB)
        lines.append("")
        for i, action in enumerate(action_plan[:5], 1):
            lines.append(f"  {i}. ▶  {action}")
        lines.append("")

    lines.append("")
    lines.append("💬  Ask another question anytime")

    return {"summary": "\n".join(lines), "full_report": []}


# ═══════════════════════════════════════════════════════════════════
# GENERIC / FALLBACK
# ═══════════════════════════════════════════════════════════════════

def _format_generic(analysis: dict) -> dict:
    summary_text = analysis.get("summary", "")
    follow_up = analysis.get("follow_up_answer", "")

    lines = []
    lines.append("📋  ANALYSIS RESULT")
    lines.append(DIVIDER_MAIN)
    lines.append("")

    if summary_text:
        for sentence in _split_sentences(summary_text):
            lines.append(f"  {sentence}")
    if follow_up:
        lines.append("")
        for sentence in _split_sentences(follow_up):
            lines.append(f"  {sentence}")
    if not summary_text and not follow_up:
        lines.append("  Analysis complete. No detailed results available.")

    lines.append("")
    return {"summary": "\n".join(lines), "full_report": []}


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _append_course_block(lines: list, index: int, rec: dict, show_candidate: bool = False):
    """
    Append a single course recommendation block.
    Each piece of info gets its own line — no dense stacking.
    """
    skill = rec.get("skill", "")
    priority = rec.get("priority", "medium")
    course_name = rec.get("course_name", "")
    platform = rec.get("platform", "")
    url = rec.get("url", "")
    reason = rec.get("reason", "")
    for_cand = rec.get("for_candidate", "")
    topics = rec.get("learning_topics", [])
    emoji = priority_emoji(priority)

    # Header line
    header = f"  {index}. {emoji}  {skill}  [{priority.upper()}]"

    if show_candidate and for_cand:
        cand_label = {
            "resume_a": "Resume A",
            "Resume A": "Resume A",
            "resume_b": "Resume B",
            "Resume B": "Resume B",
            "both": "Both",
        }.get(for_cand, for_cand)
        header += f"  (For: {cand_label})"

    lines.append(header)

    if reason:
        lines.append(f"     📌  {reason}")

    if course_name:
        plat_str = f" • {platform}" if platform else ""
        lines.append(f"     🎓  {course_name}{plat_str}")

    if url:
        lines.append(f"     🔗  {url}")
    elif topics:
        lines.append(f"     💡  Focus: {', '.join(topics[:4])}")

    lines.append("")


def _split_sentences(text: str, max_sentences: int = 5) -> list[str]:
    """
    Break a block of text into short, individual sentences.
    Prevents dense paragraphs in Telegram output.
    """
    if not text:
        return []

    text = text.strip()

    # Split on sentence boundaries
    import re
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)

    # Filter out empty strings and limit
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    return sentences[:max_sentences]


def _validate_presentation(text: str) -> str:
    """
    Final presentation check before returning to Telegram.

    Rules enforced:
      ✓ No triple+ blank lines (collapse to double)
      ✓ No trailing whitespace on lines
      ✓ Sections are visually separated
      ✓ No unnecessarily long lines (soft wrap guidance)
      ✓ Clean start and end
    """
    if not text:
        return text

    import re

    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in text.split("\n")]

    # Collapse 3+ consecutive blank lines to exactly 2
    cleaned = []
    blank_count = 0
    for line in lines:
        if line == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append(line)
        else:
            blank_count = 0
            cleaned.append(line)

    # Remove leading/trailing blank lines
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    return "\n".join(cleaned)


def split_into_pages(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """
    Split a long text into pages that fit Telegram's message limit.
    Splits at section boundaries (double newlines) for clean breaks.
    """
    if len(text) <= max_length:
        return [text]

    pages = []
    current = ""

    for block in text.split("\n\n"):
        candidate = current + block + "\n\n" if current else block + "\n\n"

        if len(candidate) > max_length:
            if current:
                pages.append(current.strip())
            current = block + "\n\n"
        else:
            current = candidate

    if current.strip():
        pages.append(current.strip())

    return pages


def get_page_footer(current_page: int, total_pages: int) -> str:
    """Return a clean footer indicating the current page in a multi-page report."""
    if total_pages <= 1:
        return ""
    return f"\n\n📄  Page {current_page} of {total_pages}"

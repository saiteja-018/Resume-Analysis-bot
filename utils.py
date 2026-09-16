"""
Utility helpers for CareerMatch AI bot.
Text processing, JSON extraction, and Telegram formatting utilities.
"""

import json
import re


def clean_text(text: str) -> str:
    """Normalize whitespace and remove non-printable characters."""
    if not text:
        return ""
    # Remove null bytes and non-printable chars (keep newlines, tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Normalize multiple blank lines to at most two
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Normalize multiple spaces to single space (preserve newlines)
    text = re.sub(r'[^\S\n]+', ' ', text)
    # Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    return text.strip()


def truncate_text(text: str, max_chars: int) -> str:
    """Smart truncation — avoids cutting mid-sentence."""
    if not text or len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Try to cut at the last sentence boundary
    last_period = truncated.rfind('.')
    last_newline = truncated.rfind('\n')
    cut_point = max(last_period, last_newline)
    if cut_point > max_chars * 0.7:  # Only if the boundary is reasonably close
        truncated = truncated[:cut_point + 1]
    return truncated + "\n[...truncated]"


def extract_json_from_text(text: str) -> dict | None:
    """
    Extract JSON from text that might contain markdown fences or extra content.
    Returns parsed dict or None if extraction fails.
    """
    if not text:
        return None

    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try to extract from markdown code fences
    patterns = [
        r'```json\s*\n?(.*?)\n?\s*```',  # ```json ... ```
        r'```\s*\n?(.*?)\n?\s*```',        # ``` ... ```
        r'\{[\s\S]*\}',                     # Bare JSON object
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                json_str = match.group(1) if match.lastindex else match.group(0)
                return json.loads(json_str.strip())
            except (json.JSONDecodeError, IndexError):
                continue

    # Last resort: find the first { and last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    return None


def is_valid_json(text: str) -> bool:
    """Check if a string is valid JSON."""
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2 format."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    escaped = ""
    for char in text:
        if char in special_chars:
            escaped += f'\\{char}'
        else:
            escaped += char
    return escaped


def format_score_bar(score: int, max_score: int = 100, bar_length: int = 10) -> str:
    """Create a visual score bar using block characters."""
    if max_score == 0:
        return "░" * bar_length
    filled = round((score / max_score) * bar_length)
    filled = min(filled, bar_length)
    empty = bar_length - filled
    return "█" * filled + "░" * empty


def score_emoji(score: int) -> str:
    """Return an emoji based on the score range."""
    if score >= 90:
        return "🟢"
    elif score >= 80:
        return "🟢"
    elif score >= 70:
        return "🟡"
    elif score >= 60:
        return "🟠"
    elif score >= 50:
        return "🔴"
    else:
        return "⛔"


def priority_emoji(priority: str) -> str:
    """Return an emoji for priority level."""
    mapping = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
    }
    return mapping.get(priority.lower(), "⚪")


def status_emoji(status: str) -> str:
    """Return an emoji for skill match status."""
    mapping = {
        "matched": "✅",
        "partial": "⚠️",
        "missing": "❌",
        "unclear": "❓",
    }
    return mapping.get(status.lower(), "⚪")


def is_job_description_doc(filename: str, text: str) -> bool:
    """
    Determine whether an uploaded document (docx or pdf) is a Job Description
    based on filename hints and text content patterns.
    """
    lower_name = (filename or "").lower()

    # 1. Strong filename indicators
    jd_filename_tokens = [
        "jd", "job_description", "job-description", "jobdescription", "job description",
        "job_spec", "job-spec", "jobspec", "job spec",
        "job_posting", "job-posting", "jobposting", "job posting",
        "role_description", "role-description", "roledescription", "role description",
        "position_description", "position-description",
        "job_profile", "job-profile", "job profile",
        "job_details", "job-details", "job details",
        "vacancy", "hiring", "job_requirement", "job_requirements"
    ]
    for token in jd_filename_tokens:
        if re.search(r'(^|[_\-\s\.\(\[\d])' + re.escape(token) + r'([_\-\s\.\)\]\d]|$)', lower_name):
            return True

    # 2. Content-based classification
    lower_text = (text or "").lower()
    if len(lower_text) < 50:
        return False

    jd_keywords = [
        "job description", "job title", "about the job", "about the role",
        "role overview", "position overview", "job summary", "role summary",
        "responsibilities", "key responsibilities", "core responsibilities",
        "what you'll do", "what you will do", "what you bring", "who you are",
        "requirements", "minimum requirements", "basic requirements", "key requirements",
        "qualifications", "minimum qualifications", "preferred qualifications",
        "desired qualifications", "must have", "nice to have", "good to have",
        "what we offer", "what we're looking for", "what we are looking for",
        "about us", "who we are", "why join us", "benefits & perks", "benefits:",
        "compensation", "salary range", "equal opportunity employer",
        "reporting to", "location:", "employment type", "full-time", "part-time"
    ]

    resume_keywords = [
        "curriculum vitae", "resume", "work experience", "professional experience",
        "employment history", "education", "b.tech", "b.e.", "bachelor of",
        "master of", "gpa", "cgpa", "academic background", "personal projects",
        "technical skills", "skills summary", "certifications", "achievements",
        "career objective", "personal profile", "declaration", "my experience"
    ]

    jd_score = sum(1 for kw in jd_keywords if kw in lower_text)
    resume_score = sum(1 for kw in resume_keywords if kw in lower_text)

    if jd_score >= 3 and jd_score > resume_score:
        return True
    if jd_score >= 2 and any(term in lower_name for term in ("job", "role", "spec", "req", "desc", "position")):
        return True

    return False

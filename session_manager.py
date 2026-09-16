"""
Session manager for CareerMatch AI bot.
Tracks per-user state across multi-step conversation flows.
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from config import SESSION_TIMEOUT

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """Possible states for a user session."""
    IDLE = "idle"
    WAITING_RESUME = "waiting_resume"
    WAITING_RESUME_B = "waiting_resume_b"
    WAITING_JD = "waiting_jd"
    WAITING_QUESTION = "waiting_question"
    ANALYZING = "analyzing"


class SessionMode(Enum):
    """The analysis mode the user initiated."""
    NONE = "none"
    ANALYZE = "analyze"           # Resume vs JD
    REVIEW = "review"             # Resume only
    COMPARE = "compare"           # Two resumes (optionally + JD)
    JD_ONLY = "jd_only"           # JD analysis only
    FOLLOW_UP = "follow_up"       # Follow-up question


@dataclass
class ResumeItem:
    """Represents a single resume document in a multi-resume session."""
    index: int
    name: str  # e.g., "Resume 1 (john_doe.pdf)"
    filename: str
    text: str


@dataclass
class UserSession:
    """Holds all data for a single user's interaction session."""
    user_id: int
    state: SessionState = SessionState.IDLE
    mode: SessionMode = SessionMode.NONE
    resumes: list[ResumeItem] = field(default_factory=list)
    jd_text: str | None = None
    last_analysis: dict | None = None
    last_updated: float = field(default_factory=time.time)

    # ── Backward compatibility properties ──
    @property
    def resume_a_text(self) -> str | None:
        return self.resumes[0].text if len(self.resumes) > 0 else None

    @resume_a_text.setter
    def resume_a_text(self, val: str | None):
        if val is None:
            if self.resumes:
                self.resumes.pop(0)
        elif self.resumes:
            self.resumes[0].text = val
        else:
            self.resumes.append(ResumeItem(index=1, name="Resume 1", filename="resume_1", text=val))

    @property
    def resume_b_text(self) -> str | None:
        return self.resumes[1].text if len(self.resumes) > 1 else None

    @resume_b_text.setter
    def resume_b_text(self, val: str | None):
        if val is None:
            if len(self.resumes) > 1:
                self.resumes.pop(1)
        elif len(self.resumes) > 1:
            self.resumes[1].text = val
        else:
            self.resumes.append(ResumeItem(index=2, name="Resume 2", filename="resume_2", text=val))

    def add_resume(self, text: str, filename: str = "") -> ResumeItem:
        """Add a resume to the session's candidate pool."""
        idx = len(self.resumes) + 1
        name = f"Resume {idx}"
        if filename:
            name += f" ({filename})"
        item = ResumeItem(index=idx, name=name, filename=filename or f"resume_{idx}", text=text)
        self.resumes.append(item)
        self.touch()
        return item

    def resume_count(self) -> int:
        return len(self.resumes)

    def clear_resumes(self):
        self.resumes.clear()
        self.touch()

    def reset(self):
        """Clear all session inputs and return to idle."""
        self.state = SessionState.IDLE
        self.mode = SessionMode.NONE
        self.resumes.clear()
        self.jd_text = None
        # Keep last_analysis for follow-up questions
        self.last_updated = time.time()

    def full_reset(self):
        """Clear everything including last analysis."""
        self.reset()
        self.last_analysis = None

    def touch(self):
        """Update the timestamp."""
        self.last_updated = time.time()

    def is_expired(self) -> bool:
        """Check if the session has timed out."""
        return (time.time() - self.last_updated) > SESSION_TIMEOUT

    def has_resume(self) -> bool:
        return len(self.resumes) > 0

    def has_jd(self) -> bool:
        return bool(self.jd_text)

    def has_previous_analysis(self) -> bool:
        return bool(self.last_analysis)

    def get_status_summary(self) -> str:
        """Return a human-readable summary of the current session state."""
        parts = []
        if self.resumes:
            parts.append(f"Resumes loaded: {len(self.resumes)}")
            for r in self.resumes[:5]:
                parts.append(f"  • {r.name}: {len(r.text)} chars")
            if len(self.resumes) > 5:
                parts.append(f"  ...and {len(self.resumes) - 5} more")
        if self.jd_text:
            parts.append(f"Job Description: {len(self.jd_text)} chars")
        if self.last_analysis:
            parts.append(f"Last analysis: {self.last_analysis.get('analysis_type', 'unknown')}")
        parts.append(f"State: {self.state.value}")
        parts.append(f"Mode: {self.mode.value}")
        return "\n".join(parts) if parts else "Session is empty."


class SessionManager:
    """Manages user sessions with auto-cleanup of expired sessions."""

    def __init__(self):
        self._sessions: dict[int, UserSession] = {}
        self._last_cleanup: float = time.time()
        self._cleanup_interval: int = 300  # 5 minutes

    def get(self, user_id: int) -> UserSession:
        """Get or create a session for a user."""
        self._maybe_cleanup()

        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(user_id=user_id)
            logger.debug(f"Created new session for user {user_id}")

        session = self._sessions[user_id]

        # Auto-reset expired sessions
        if session.is_expired():
            logger.info(f"Session expired for user {user_id}, resetting.")
            session.full_reset()

        session.touch()
        return session

    def remove(self, user_id: int):
        """Remove a user's session entirely."""
        self._sessions.pop(user_id, None)

    def _maybe_cleanup(self):
        """Periodically clean up expired sessions."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        expired = [
            uid for uid, session in self._sessions.items()
            if session.is_expired()
        ]
        for uid in expired:
            del self._sessions[uid]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions.")

        self._last_cleanup = now

    @property
    def active_count(self) -> int:
        return len(self._sessions)


# Global session manager instance
sessions = SessionManager()

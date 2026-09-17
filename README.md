# 🤖 CareerMatch AI — Telegram ATS Resume Analyzer Bot

An intelligent Telegram chatbot that analyzes resumes against job descriptions, identifies skill gaps, detects resume problems, compares candidates, and recommends learning paths with direct course links — powered by AI.

---

## ✨ Features

### 📊 Resume vs JD Analysis
Match your resume against any job description. Get a detailed ATS compatibility score (0–100) with category breakdowns: skill match, keyword coverage, experience relevance, education, readability, and impact.

### 📝 Resume Quality Review
Upload a resume without a specific job — get a comprehensive quality review with issue detection, strength identification, and actionable improvement suggestions.

### 🔄 Resume Comparison
Compare two resumes side by side with category-level scoring, per-candidate strengths and improvement areas, and a clear winner verdict.

### 📋 JD Analysis
Analyze a job description to extract required/preferred skills, important keywords, likely interview topics, and preparation guidance.

### 💬 Follow-Up Intelligence
Ask any follow-up question after an analysis. The bot acts as an elite career coach — providing concrete bullet rewrites, interview prep, and project suggestions tailored to your actual background.

### 🎓 Course Recommendations
Every analysis includes curated course recommendations with direct links (Coursera, Udemy, edX, freeCodeCamp, official docs) for identified skill gaps.

### 📎 Smart File Upload
Upload PDF or DOCX files directly in Telegram. The bot automatically detects whether an uploaded document is a resume or a job description based on filename and content patterns.

### 🛡️ Anti-Hallucination Engine
Strict rules prevent the AI from fabricating skills, metrics, technologies, or experience. Missing skills are reported as "Not found in resume" — never as "Candidate does not know this."

### 📱 Telegram Presentation Engine
Reports are formatted specifically for Telegram readability:
- Clean spacing between every section
- Short sentences — one idea per line
- Visual hierarchy with Unicode dividers
- Scores displayed prominently on their own line
- Issues ordered by priority (critical → low)
- Mobile-optimized line lengths
- Automatic presentation validation before output

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Runtime** | Python 3.10+ |
| **Bot Framework** | python-telegram-bot ≥21.0 (async) |
| **AI Providers** | Groq (LPU) or TokenRouter (OpenAI-compatible) |
| **PDF Parsing** | pdfplumber |
| **DOCX Parsing** | python-docx |
| **Rate Limiting** | Token-bucket per-user limiter |

---

## 🚀 Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/saiteja-018/Resume-Analysis-bot.git
cd Resume-Analysis-bot
pip install -r requirements.txt
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Get from [@BotFather](https://t.me/BotFather) on Telegram |
| `GROQ_API_KEY` | ✅* | Your API key from [console.groq.com](https://console.groq.com) |
| `TOKENROUTER_API_KEY` | ✅* | Alternative: API key from [tokenrouter.com](https://tokenrouter.com) |
| `AI_MODEL` | ❌ | Model name (default: auto-detected based on provider) |

> *Provide either `GROQ_API_KEY` or `TOKENROUTER_API_KEY`. Groq is used if both are set.

### 3. Run the bot

```bash
python bot.py
```

### 4. Run with Docker (alternative)

```bash
# Build and start
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## 📖 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and feature overview |
| `/analyze` | Start resume vs JD analysis |
| `/review` | Resume quality review (no JD needed) |
| `/compare` | Compare two resumes side by side |
| `/jd` | Analyze a job description |
| `/status` | Check current session status |
| `/reset` | Clear session and start fresh |
| `/help` | Usage guide |

---

## 📁 Project Structure

```
├── bot.py                  # Telegram bot entry point & all handlers
├── config.py               # Configuration & environment loading
├── ai_engine.py            # AI API client (Groq / TokenRouter)
├── document_parser.py      # PDF & DOCX text extraction
├── session_manager.py      # Per-user session state management
├── response_formatter.py   # Telegram Presentation Engine
├── prompts.py              # AI system prompt & message builder
├── utils.py                # Utility helpers (scoring, emoji, text)
├── rate_limiter.py         # Token-bucket rate limiter
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container build
├── docker-compose.yml      # Docker Compose config
├── .env.example            # Environment variable template
└── README.md
```

---

## ⚙️ Configuration

All settings are configured via environment variables (`.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Telegram bot token |
| `GROQ_API_KEY` | *(required\*)* | Groq API key |
| `TOKENROUTER_API_KEY` | *(required\*)* | TokenRouter API key (alternative to Groq) |
| `AI_MODEL` | Auto-detected | AI model name |
| `AI_BASE_URL` | Auto-detected | API base URL |
| `MAX_RESUME_LENGTH` | `8000` | Max characters sent to AI per resume |
| `MAX_JD_LENGTH` | `4000` | Max characters for job descriptions |
| `SESSION_TIMEOUT` | `3600` | Session expiry in seconds (1 hour) |

---

## 📊 ATS Scoring Model

The bot calculates an estimated ATS compatibility score using weighted categories:

| Category | Weight |
|----------|--------|
| Required Skill Match | 35% |
| Keyword / Semantic Match | 20% |
| Experience / Project Relevance | 15% |
| Education / Certification Match | 10% |
| ATS Readability | 10% |
| Achievement / Impact | 10% |

**Score Interpretation:**

| Range | Level |
|-------|-------|
| 90–100 | 🟢 Excellent match |
| 80–89 | 🟢 Strong match |
| 70–79 | 🟡 Good match with gaps |
| 60–69 | 🟠 Moderate match |
| 50–59 | 🔴 Weak match |
| 0–49 | ⛔ Poor match |

> ⚠️ This is an **estimated** ATS compatibility score — not a real ATS score, hiring probability, or interview guarantee.

---

## 📝 License

MIT

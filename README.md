# 🤖 CareerMatch AI — Telegram ATS Resume Analyzer Bot

An intelligent Telegram chatbot that analyzes resumes, compares them against job descriptions, identifies skill gaps, detects resume problems, and recommends learning paths — powered by AI.

## ✨ Features

- **📊 Resume vs JD Analysis** — Match your resume against any job description with detailed ATS scoring
- **📝 Resume Review** — Get a comprehensive quality review without a specific job
- **🔄 Resume Comparison** — Compare two resumes side by side
- **📋 JD Analysis** — Analyze a job description for required skills, keywords & interview topics
- **💬 Follow-up Questions** — Ask clarifying questions after any analysis
- **📎 File Support** — Upload PDF or DOCX resumes directly in Telegram

## 🛠️ Tech Stack

- **Python 3.10+**
- **python-telegram-bot** — Async Telegram Bot API
- **OpenAI SDK** — For TokenRouter API (GLM-5.3 model)
- **pdfplumber** — PDF text extraction
- **python-docx** — DOCX text extraction

## 🚀 Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd Resume-Analysis-bot
pip install -r requirements.txt
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Get from [@BotFather](https://t.me/BotFather) on Telegram |
| `TOKENROUTER_API_KEY` | Your API key from [tokenrouter.com](https://tokenrouter.com) |
| `AI_MODEL` | Model to use (default: `z-ai/glm-5.3-free`) |

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

## 📖 Usage

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/analyze` | Start resume vs JD analysis |
| `/review` | Resume quality review |
| `/compare` | Compare two resumes |
| `/jd` | Analyze a job description |
| `/status` | Check session status |
| `/reset` | Clear session |
| `/help` | Usage guide |

## 📁 Project Structure

```
├── bot.py                  # Telegram bot entry point & handlers
├── config.py               # Configuration & env loading
├── ai_engine.py            # AI API client (TokenRouter)
├── document_parser.py      # PDF & DOCX text extraction
├── session_manager.py      # Per-user session management
├── response_formatter.py   # JSON → Telegram messages
├── prompts.py              # AI system prompt
├── utils.py                # Utility helpers
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
└── README.md               # This file
```

## ⚙️ Configuration

All settings are configured via environment variables (`.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | (required) | Telegram bot token |
| `TOKENROUTER_API_KEY` | (required) | TokenRouter API key |
| `AI_MODEL` | `z-ai/glm-5.3-free` | AI model to use |
| `MAX_RESUME_LENGTH` | `8000` | Max chars sent to AI per resume |
| `MAX_JD_LENGTH` | `4000` | Max chars for job descriptions |
| `SESSION_TIMEOUT` | `3600` | Session expiry in seconds |

## 📝 License

MIT

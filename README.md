# 🥊 Objection Killer Agent

> **A real-time sales coaching agent that listens to live calls, detects objections in under 1.5 seconds, and pushes private cue cards to the rep's dashboard via WebSocket — without the prospect ever knowing.**

---

## 📸 Overview

When a prospect says *"it's too expensive"* or *"we already use Salesforce"*, most reps freeze or fumble. Objection Killer listens to the live call transcript, detects the objection type in under 1.5 seconds using deterministic pattern matching (no LLM latency on the critical path), and instantly pushes a private cue card to the rep's dashboard — headline, rebuttal, talk track, and proof points — sourced from your own knowledge base.

The prospect hears a confident rep. They never see the cards.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Live Call Audio Stream (microphone)            │
│              POST /sessions/{id}/audio (chunked WAV)        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   FastAPI + WebSocket                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Whisper STT (OpenAI / local)                        │   │
│  │  Transcribes audio chunks in real-time               │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │  SessionTranscriptBuffer (bounded 1800-char window)  │   │
│  │  Rolling context window for low-latency detection    │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │  ObjectionDetector (deterministic, <1.5s)            │   │
│  │  Regex + weighted phrase matching, NO LLM latency    │   │
│  │  7 objection types: pricing · competitor · feature · │   │
│  │  timeline · authority · trust · integration          │   │
│  │  Confidence scored 0.0–1.0 per detection            │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │  CueEngine (knowledge base search)                   │   │
│  │  Retrieves best-matching KnowledgeItems per objection│   │
│  │  Composes: headline · rebuttal · talk_track ·        │   │
│  │  proof_points · source_titles                        │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │  CueHub (WebSocket fanout)                           │   │
│  │  Pushes CueCard to rep's private dashboard instantly  │   │
│  │  Multi-rep support — each rep gets their own cards   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

Rep Dashboard (dashboard.html — private, prospect never sees it)
```

---

## 🎯 7 Objection Types Detected

| Type | Example Trigger Phrases |
|------|------------------------|
| `pricing` | "too expensive", "not in our budget", "can't afford" |
| `competitor` | "we already use Salesforce", "HubSpot is cheaper" |
| `feature` | "does it support SSO?", "missing feature", "can it integrate?" |
| `timeline` | "not a priority", "next quarter", "too busy right now" |
| `authority` | "need to check with my manager", "not my decision" |
| `trust` | "how do I know it works?", "seen too many demos" |
| `integration` | "won't fit our stack", "API?", "Zapier?" |

---

## 💬 Sample Cue Card

When prospect says: *"It's too expensive, we were looking at something cheaper"*

```
🟡 PRICING: use ROI Calculator Case Study

Rebuttal:
"Totally fair — let me put this in perspective. Most teams 
 using us recover the cost in under 6 weeks from reduced 
 manual follow-up alone."

Talk Track:
1. Acknowledge: "I hear you — budget is always a real constraint."
2. Quantify: "Our median customer saves 14 hours/week on manual tasks."
3. Redirect: "Can I show you the 90-day ROI breakdown for a team your size?"

Proof Points:
• Case Study: SaaS co reduced CAC by 34% in Q1
• 93% of customers see ROI within 60 days
• Free trial — no card required

Source: pricing_objection_playbook · roi_calculator_deck
```

---

## 📁 Folder Structure

```
objection-killer-agent/
├── app/
│   ├── main.py              # FastAPI app — sessions, audio, WebSocket, knowledge
│   ├── detector.py          # ObjectionDetector — deterministic regex engine
│   ├── cue_engine.py        # CueEngine — knowledge search + card composition
│   ├── hub.py               # CueHub — WebSocket fanout to rep dashboards
│   ├── stt.py               # Whisper STT (OpenAI API / local fallback)
│   ├── auth.py              # API key auth
│   ├── db.py                # SQLite async — sessions, knowledge, cue cards
│   ├── models.py            # Pydantic models (ObjectionSignal, CueCard, etc.)
│   ├── config.py            # Settings
│   └── templates/
│       ├── dashboard.html   # Rep's private live cue card dashboard
│       └── capture.html     # Audio capture UI (microphone stream)
├── tests/
│   ├── test_detector.py     # Objection detection unit tests
│   └── test_cue_engine.py   # Cue card composition tests
├── scripts/
│   └── seed_demo_data.py    # Seed knowledge base with demo playbooks
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

---

## ⚡ Quick Start

### 1. Clone & Configure
```bash
git clone <repo-url>
cd objection-killer-agent
cp .env.example .env
# Add OPENAI_API_KEY (for Whisper STT)
```

### 2. Run with Docker
```bash
docker-compose up --build
```

### 3. Run Locally
```bash
pip install -e .
uvicorn app.main:app --reload
```

### 4. Seed Knowledge Base
```bash
python scripts/seed_demo_data.py
```

### 5. Open Rep Dashboard
```
http://localhost:8000/dashboard/{rep_id}
```

### 6. Start a Session
```bash
curl -X POST http://localhost:8000/sessions \
  -H "X-API-Key: your-key" \
  -d '{"rep_id": "rep_01", "prospect_name": "Acme Corp"}'
```

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions` | Start a new call session |
| `POST` | `/sessions/{id}/audio` | Stream audio chunk → detect + push card |
| `POST` | `/sessions/{id}/transcript` | Push transcript text directly (no STT) |
| `GET` | `/sessions/{id}/cards` | Get all cue cards for a session |
| `WS` | `/ws/{rep_id}` | WebSocket — rep's private dashboard connection |
| `POST` | `/knowledge` | Add a knowledge item to the playbook |
| `GET` | `/knowledge` | List knowledge base items |
| `GET` | `/health` | Health check |

---

## ⚙️ Configuration

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Whisper STT (optional — accepts raw transcript too) |
| `STT_PROVIDER` | `openai` or `local` |
| `DETECTION_CONFIDENCE_THRESHOLD` | Min confidence to trigger card (default: 0.65) |
| `TRANSCRIPT_BUFFER_CHARS` | Rolling window size (default: 1800) |
| `MAX_CARDS_PER_OBJECTION` | Knowledge items per card (default: 3) |

---

## 🚀 Scaling Path

| Stage | Upgrade |
|-------|---------|
| **Now** | SQLite + single rep dashboard |
| **Sales team** | PostgreSQL + multi-rep sessions, call recording replay |
| **SaaS** | Zoom/Meet/Teams integration, per-team playbooks, analytics |
| **Enterprise** | CRM auto-log (HubSpot/Salesforce), manager coaching dashboard |

---

## 📦 Built With

- **FastAPI + WebSocket** — Real-time cue card delivery
- **Whisper (OpenAI)** — Speech-to-text transcription
- **Deterministic Regex Engine** — Sub-1.5s objection detection (no LLM latency)
- **SQLite async** — Session + knowledge + card persistence
- **Pydantic v2** — Strictly typed models
- **pytest** — Detector + cue engine test suite
- **Docker** — Reproducible deployment

---

*Day 19/27 — Built by Pranav | IIT Kharagpur · AI Automation Agency*
# voice-assistant-for-ecommerce

## ShopVoice — Voice Shopping Assistant
### Built for Murf Falcon TTS Hackathon

A voice-first e-commerce assistant powered by Murf Falcon TTS, Gemini LLM, and Web Speech API.

---

## Features

- **Voice product search** — Speak naturally to find products (e.g. "Gift for mom under ₹1500")
- **Add to cart by voice** — Say "Add the first one" or "Pehla wala add karo"
- **Multilingual** — Understands English and Hindi/Hinglish, responds in same language via Murf
- **Voice checkout** — "Checkout" → AI reads total → say "Yes/Haan" to confirm order

---

## Project Structure

```
voice-shopping-assistant/
├── backend/
│   ├── main.py          # FastAPI server (chat + TTS endpoints)
│   ├── products.py      # Mock product catalog + search logic
│   ├── requirements.txt
│   └── .env.example     # Copy to .env and fill in API keys
├── frontend/
│   ├── index.html
│   ├── app.js           # Full voice loop logic
│   └── style.css
└── README.md
```

---

## Setup

### 1. Get API Keys
- **Murf API key**: Sign up at https://murf.ai → Dashboard → API Keys
- **Gemini API key**: https://aistudio.google.com/app/apikey

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MURF_API_KEY and GEMINI_API_KEY
uvicorn main:app --reload --port 8000
```

### 3. Frontend

Open `frontend/index.html` in Chrome (use Live Server in VS Code or any local server).

> **Important**: Use Chrome — Web Speech API is best supported there.

---

## Voice Commands

| What you say | What happens |
|---|---|
| "Gift for mom under ₹1500" | Searches + shows products |
| "Fitness gear" | Searches fitness category |
| "Add the first one" / "Pehla add karo" | Adds 1st product to cart |
| "Add second one" / "Doosra wala" | Adds 2nd product to cart |
| "Checkout" / "Order karna hai" | Reads cart total, asks confirmation |
| "Yes" / "Haan" / "Confirm" | Places order |
| "No" / "Nahi" / "Cancel" | Cancels checkout |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Voice output | Murf Falcon TTS (streaming, ~130ms latency) |
| Voice input | Web Speech API (en-IN — supports Hindi) |
| LLM / Intent | Google Gemini 1.5 Flash |
| Backend | FastAPI + Python |
| Frontend | Vanilla HTML/CSS/JS |

---

## Murf Falcon Voice Config

- **English**: `en-US-natalie` — Conversational style
- **Hindi**: `hi-IN-shweta` — Conversational style

Language is auto-detected from user speech and the correct Murf voice is used automatically.

import os
import json
import re
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import google.generativeai as genai
from products import search_products, get_product_by_index

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest"))


def _detect_language(text: str) -> str:
    lower = text.lower()
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    hindi_markers = ["haan", "nahi", "karo", "chahiye", "andar", "wala", "doosra", "teesra", "pehla"]
    if any(marker in lower for marker in hindi_markers):
        return "hi"
    return "en"


def _extract_budget(text: str):
    match = re.search(r"(?:₹|rs\.?\s*)?(\d{3,6})", text.lower())
    return int(match.group(1)) if match else None


def _extract_keywords(text: str):
    stopwords = {
        "for", "the", "and", "with", "under", "below", "gift", "add", "cart", "to", "me", "show",
        "please", "want", "need", "my", "one", "first", "second", "third", "checkout", "order", "items"
    }
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in stopwords]


def _fallback_intent_response(user_message: str, awaiting_confirmation: bool, preferred_language: str = "auto"):
    lower = user_message.lower()
    language = preferred_language if preferred_language in ["en", "hi", "te", "kn", "mr"] else _detect_language(user_message)

    if awaiting_confirmation and any(token in lower for token in ["yes", "haan", "confirm", "ok", "proceed"]):
        return {
            "intent": "confirm_order",
            "keywords": [],
            "max_budget": None,
            "cart_item_index": None,
            "language": language,
            "reply": (
                "Great, confirming your order now." if language == "en"
                else "Theek hai, order confirm kar raha hoon." if language == "hi"
                else "Sare, mi order confirm chesthunnanu." if language == "te"
                else "Sari, nanu order confirm madtini." if language == "kn"
                else "Barobar, mi order confirm karto."
            ),
            "confirm_checkout": True
        }

    if awaiting_confirmation and any(token in lower for token in ["no", "nahi", "cancel"]):
        return {
            "intent": "cancel_order",
            "keywords": [],
            "max_budget": None,
            "cart_item_index": None,
            "language": language,
            "reply": (
                "Okay, I have cancelled it." if language == "en"
                else "Theek hai, maine cancel kar diya." if language == "hi"
                else "Sare, nenu cancel chesanu." if language == "te"
                else "Sari, nanu cancel madidini." if language == "kn"
                else "Thik aahe, mi cancel kele."
            ),
            "confirm_checkout": False
        }

    if any(token in lower for token in ["checkout", "order", "place order", "buy", "bill", "pay"]):
        return {
            "intent": "checkout",
            "keywords": [],
            "max_budget": None,
            "cart_item_index": None,
            "language": language,
            "reply": (
                "Ready to place your order." if language == "en"
                else "Order place karne ke liye ready hoon." if language == "hi"
                else "Mee order place cheyadaniki ready." if language == "te"
                else "Nimma order place madalu ready." if language == "kn"
                else "Tumcha order place karayla ready aahe."
            ),
            "confirm_checkout": True
        }

    if any(token in lower for token in ["add", "cart", "pehla", "doosra", "teesra", "first", "second", "third"]):
        index = None
        if any(token in lower for token in ["first", "1", "pehla"]):
            index = 0
        elif any(token in lower for token in ["second", "2", "doosra"]):
            index = 1
        elif any(token in lower for token in ["third", "3", "teesra"]):
            index = 2

        return {
            "intent": "add_to_cart",
            "keywords": [],
            "max_budget": None,
            "cart_item_index": index,
            "language": language,
            "reply": (
                "Adding that item to your cart." if language == "en"
                else "Main item cart mein add kar raha hoon." if language == "hi"
                else "Aa item ni mee cart lo add chesthunna." if language == "te"
                else "Aa item na nimma cart ge add madtini." if language == "kn"
                else "To item tumchya cart madhe add karto."
            ),
            "confirm_checkout": False
        }

    return {
        "intent": "search",
        "keywords": _extract_keywords(user_message),
        "max_budget": _extract_budget(user_message),
        "cart_item_index": None,
        "language": language,
        "reply": (
            "Here are a few options you might like." if language == "en"
            else "Yeh kuch options aapke liye hain." if language == "hi"
            else "Mee kosam konni options unnayi." if language == "te"
            else "Nimagagi kelavu options ive." if language == "kn"
            else "Tumchya sathi kahi options aahet."
        ),
        "confirm_checkout": False
    }

# ─── Murf voice config ───────────────────────────────────────────────
VOICE_CONFIG = {
    "en": {
        "voiceId": "en-US-natalie",
        "style": "Conversational"
    },
    "hi": {
        "voiceId": "hi-IN-shweta",
        "style": "Conversational"
    }
}

# ─── System prompt ────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are ShopVoice, a friendly bilingual voice shopping assistant.
You understand English and Hindi (including Hinglish - mixed Hindi-English).

Analyze the user message and respond ONLY with valid JSON in this format:
{
  "intent": "search" | "add_to_cart" | "checkout" | "confirm_order" | "cancel_order" | "greeting" | "other",
  "keywords": ["keyword1", "keyword2"],
  "max_budget": 2000,
  "cart_item_index": null,
    "language": "en" | "hi" | "te" | "kn" | "mr",
  "reply": "Your warm conversational response here",
  "confirm_checkout": false
}

Rules:
- "intent" = "search" when user wants to find products
- "intent" = "add_to_cart" when user says things like "add the first one", "add second one", "pehla wala add karo", "cart mein dalo"
- "intent" = "checkout" when user wants to place order / pay — respond with confirm_checkout: true and ask them to confirm
- "intent" = "confirm_order" when user confirms with "yes", "haan", "confirm", "ok proceed"
- "intent" = "cancel_order" when user says "no", "nahi", "cancel"
- "cart_item_index": 0 for "first/pehla", 1 for "second/doosra", 2 for "third/teesra" — null otherwise
- "language": detect language among English/Hindi/Telugu/Kannada/Marathi; use "en" when uncertain
- "max_budget": extract number if budget mentioned (e.g. "2000 mein", "under 1500", "₹2000 ke andar")
- "reply" must be in the SAME language as the user (Hindi if they spoke Hindi, English if English)
- Keep reply warm, natural, under 2 sentences
- If asking a follow-up question, set intent to "other" and keywords to []
"""

@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_message = body.get("message", "")
    preferred_language = body.get("preferred_language", "auto")
    history = body.get("history", [])
    current_products = body.get("current_products", [])
    cart = body.get("cart", [])
    awaiting_confirmation = body.get("awaiting_confirmation", False)

    history_text = "\n".join([f"{m['role'].upper()}: {m['text']}" for m in history[-6:]])
    
    context = ""
    if current_products:
        context += f"\nCurrently shown products: {json.dumps(current_products)}"
    if cart:
        context += f"\nCart items: {json.dumps(cart)}"
    if awaiting_confirmation:
        context += f"\nWe are awaiting order confirmation from the user."
    if preferred_language in ["en", "hi", "te", "kn", "mr"]:
        context += f"\nRespond in {preferred_language.upper()} language."

    full_prompt = f"{SYSTEM_PROMPT}\n\nConversation so far:\n{history_text}{context}\n\nUSER: {user_message}\nASSISTANT:"

    data = None
    try:
        response = model.generate_content(full_prompt)
        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        data = json.loads(raw)
    except Exception:
        data = _fallback_intent_response(user_message, awaiting_confirmation, preferred_language)

    intent = data.get("intent", "other")
    language = data.get("language", "en")
    if preferred_language in ["en", "hi", "te", "kn", "mr"]:
        language = preferred_language
    reply = data.get("reply", "Let me help you!")
    products = []
    cart_action = None

    if intent == "search":
        keywords = data.get("keywords") or _extract_keywords(user_message)
        products = search_products(keywords, data.get("max_budget"))

    elif intent == "add_to_cart":
        index = data.get("cart_item_index")
        if index is not None and current_products:
            item = get_product_by_index(index, current_products)
            if item:
                cart_action = {"type": "add", "item": item}
            else:
                reply = "I couldn't find that item. Please try again." if language == "en" else "Woh item nahi mila. Dobara try karein."
        else:
            reply = "Please tell me which item to add — the first, second, or third one?" if language == "en" else "Kaun sa item add karein? Pehla, doosra, ya teesra?"

    elif intent == "checkout":
        if not cart:
            reply = "Your cart is empty! Add some items first." if language == "en" else "Aapka cart khali hai! Pehle kuch items add karein."
        else:
            cart_total = sum(item["price"] for item in cart)
            item_names = ", ".join([item["name"] for item in cart])
            reply = f"Your cart has {item_names}. Total: ₹{cart_total:,}. Shall I confirm the order?" if language == "en" else f"Aapke cart mein {item_names} hai. Total: ₹{cart_total:,}. Order confirm karein?"
            cart_action = {"type": "checkout_prompt"}

    elif intent == "confirm_order":
        if awaiting_confirmation and cart:
            cart_total = sum(item["price"] for item in cart)
            reply = f"Order placed! ₹{cart_total:,} will be collected on delivery. Thank you for shopping with ShopVoice!" if language == "en" else f"Order place ho gaya! ₹{cart_total:,} delivery par collect hoga. ShopVoice par shopping ke liye shukriya!"
            cart_action = {"type": "order_placed"}
        else:
            reply = "No pending order to confirm." if language == "en" else "Koi pending order nahi hai."

    elif intent == "cancel_order":
        reply = "Order cancelled. Let me know if you want to keep shopping!" if language == "en" else "Order cancel ho gaya. Agar aur shopping karni ho toh batayein!"
        cart_action = {"type": "cancel"}

    return JSONResponse({
        "reply": reply,
        "products": products,
        "intent": intent,
        "language": language,
        "cart_action": cart_action,
        "confirm_checkout": data.get("confirm_checkout", False)
    })


@app.post("/tts")
async def tts(request: Request):
    body = await request.json()
    text = body.get("text", "")
    language = body.get("language", "en")
    voice_id = body.get("voice_id")
    voice_style = body.get("voice_style")

    voice = VOICE_CONFIG.get(language, VOICE_CONFIG["en"])

    murf_url = "https://global.api.murf.ai/v1/speech/stream"
    headers = {
        "api-key": os.getenv("MURF_API_KEY"),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    payload = {
        "text": text,
        "voiceId": voice_id or voice["voiceId"],
        "model": "FALCON",
        "audioFormat": "MP3",
        "sampleRate": 24000,
        "style": voice_style or voice["style"]
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(murf_url, headers=headers, json=payload)

        if resp.status_code >= 400:
            details = {"error_message": resp.text[:400]}
            try:
                details = resp.json()
            except Exception:
                pass
            return JSONResponse(
                {"error": "TTS provider request failed", "provider_status": resp.status_code, "details": details},
                status_code=502,
            )

        content_type = (resp.headers.get("content-type") or "").lower()
        if "audio" not in content_type:
            return JSONResponse(
                {
                    "error": "TTS provider returned non-audio content",
                    "provider_status": resp.status_code,
                    "details": resp.text[:400],
                },
                status_code=502,
            )

        return Response(content=resp.content, media_type="audio/mpeg")
    except Exception as ex:
        return JSONResponse({"error": "TTS request exception", "details": str(ex)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok"}

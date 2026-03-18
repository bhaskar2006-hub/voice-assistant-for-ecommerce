const BACKEND = "http://localhost:8000";

// ── State ──────────────────────────────────────────────────────────────
let recognition = null;
let isListening = false;
let isSpeaking = false;
let conversationHistory = [];
let currentProducts = [];
let cart = [];
let awaitingConfirmation = false;
let currentLanguage = "en";
let preferredLanguage = "auto";

const RECOGNITION_LANG_MAP = {
  en: "en-IN",
  hi: "hi-IN",
  te: "te-IN",
  kn: "kn-IN",
  mr: "mr-IN"
};

const LANGUAGE_LABELS = {
  auto: "Auto",
  en: "English",
  hi: "Hindi",
  te: "Telugu",
  kn: "Kannada",
  mr: "Marathi"
};

const AUTO_FEMALE_VOICE_PROFILES = {
  en: { provider: "murf", language: "en", voiceId: "en-US-natalie", style: "Conversational", label: "Natalie Female (English)" },
  hi: { provider: "murf", language: "hi", voiceId: "hi-IN-shweta", style: "Conversational", label: "Shweta Female (Hindi)" },
  te: { provider: "browser", language: "te", voiceId: null, style: null, label: "Female Browser Voice (Telugu)" },
  kn: { provider: "browser", language: "kn", voiceId: null, style: null, label: "Female Browser Voice (Kannada)" },
  mr: { provider: "browser", language: "mr", voiceId: null, style: null, label: "Female Browser Voice (Marathi)" }
};

const BROWSER_FEMALE_VOICE_HINTS = {
  en: ["zira", "aria", "jenny", "samantha", "eva", "female"],
  hi: ["swara", "heera", "kalpana", "female"],
  te: ["telugu", "female"],
  kn: ["kannada", "female"],
  mr: ["marathi", "female"]
};

function getPreferredAssistantLanguage() {
  if (["en", "hi", "te", "kn", "mr"].includes(preferredLanguage)) return preferredLanguage;
  return currentLanguage;
}

function getRecognitionLanguage() {
  if (RECOGNITION_LANG_MAP[preferredLanguage]) {
    return RECOGNITION_LANG_MAP[preferredLanguage];
  }
  return RECOGNITION_LANG_MAP[currentLanguage] || "en-IN";
}

function getSelectedVoiceConfig() {
  const select = document.getElementById("voiceSelect");
  if (!select || select.value === "auto") return null;

  const [voiceId, style, voiceLang] = select.value.split("|");
  return { voiceId, style, voiceLang };
}

function getActiveVoiceConfig(languageForReply) {
  const selectedVoice = getSelectedVoiceConfig();
  const effectiveLanguage = languageForReply || getPreferredAssistantLanguage();

  if (!selectedVoice) {
    const profile = AUTO_FEMALE_VOICE_PROFILES[effectiveLanguage] || AUTO_FEMALE_VOICE_PROFILES.en;
    return { ...profile };
  }

  if (selectedVoice.voiceId === "browser") {
    return {
      provider: "browser",
      language: selectedVoice.voiceLang || effectiveLanguage,
      voiceId: null,
      style: null,
      label: `Browser (${LANGUAGE_LABELS[selectedVoice.voiceLang] || "Auto"})`
    };
  }

  return {
    provider: "murf",
    language: selectedVoice.voiceLang || effectiveLanguage,
    voiceId: selectedVoice.voiceId,
    style: selectedVoice.style,
    label: `Murf (${LANGUAGE_LABELS[selectedVoice.voiceLang] || "Custom"})`
  };
}

async function speakWithBrowser(text, language, statusMessage = "Speaking with browser voice...") {
  const synth = window.speechSynthesis;
  if (!synth || typeof SpeechSynthesisUtterance === "undefined") {
    throw new Error("Browser speech is not available");
  }

  const pickFemaleVoice = (targetLanguage) => {
    const locale = RECOGNITION_LANG_MAP[targetLanguage] || "en-IN";
    const baseLocale = locale.split("-")[0].toLowerCase();
    const voices = synth.getVoices() || [];
    if (!voices.length) return null;

    const localeMatched = voices.filter(v => {
      const lang = (v.lang || "").toLowerCase();
      return lang === locale.toLowerCase() || lang.startsWith(`${baseLocale}-`) || lang === baseLocale;
    });

    const nameHints = BROWSER_FEMALE_VOICE_HINTS[targetLanguage] || [];
    const femaleByName = localeMatched.find(v => {
      const name = (v.name || "").toLowerCase();
      return nameHints.some(h => name.includes(h));
    });

    if (femaleByName) return femaleByName;
    if (localeMatched.length) return localeMatched[0];

    return voices.find(v => (v.lang || "").toLowerCase().startsWith("en-")) || voices[0];
  };

  await new Promise((resolve, reject) => {
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = RECOGNITION_LANG_MAP[language] || "en-IN";
    const selectedFemaleVoice = pickFemaleVoice(language);
    if (selectedFemaleVoice) utter.voice = selectedFemaleVoice;

    utter.onend = () => {
      isSpeaking = false;
      setMicState("");
      setDot("");
      setStatus("Press mic to speak");
      resolve();
    };

    utter.onerror = () => {
      isSpeaking = false;
      setMicState("");
      setDot("");
      reject(new Error("Browser voice playback failed"));
    };

    setStatus(statusMessage);
    synth.cancel();
    synth.speak(utter);
  });
}

function onLanguageChange() {
  const select = document.getElementById("languageSelect");
  preferredLanguage = select ? select.value : "auto";

  if (recognition) {
    recognition.lang = getRecognitionLanguage();
  }

  const label = LANGUAGE_LABELS[preferredLanguage] || "Auto";
  const activeVoice = getActiveVoiceConfig(getPreferredAssistantLanguage());
  setStatus(`Language: ${label} | Voice: ${activeVoice.label}`);
}

function onVoiceChange() {
  const activeVoice = getActiveVoiceConfig(getPreferredAssistantLanguage());
  setStatus(`Voice set to ${activeVoice.label}`);
}

// ── Speech Recognition ────────────────────────────────────────────────
function setupRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    setStatus("Speech recognition not supported — use Chrome");
    return null;
  }
  const rec = new SR();
  rec.continuous = false;
  rec.interimResults = true;
  rec.lang = getRecognitionLanguage();

  rec.onresult = (e) => {
    const transcript = Array.from(e.results).map(r => r[0].transcript).join("");
    if (e.results[e.results.length - 1].isFinal) {
      handleUserInput(transcript);
    } else {
      setStatus(`Hearing: "${transcript}"`);
    }
  };
  rec.onend  = () => { if (isListening) stopListening(); };
  rec.onerror = (e) => { setStatus("Mic error: " + e.error); stopListening(); };
  return rec;
}

// ── UI helpers ─────────────────────────────────────────────────────────
function addBubble(text, role) {
  const win = document.getElementById("chatWindow");
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
}

function setStatus(msg) {
  document.getElementById("status").textContent = msg;
}

function setDot(state) {
  const dot = document.getElementById("statusDot");
  dot.className = "status-dot " + state;
}

function setMicState(state) {
  document.getElementById("micBtn").className = "mic-btn " + state;
}

function setLanguage(lang) {
  currentLanguage = ["en", "hi", "te", "kn", "mr"].includes(lang) ? lang : "en";
  const shownLang = getPreferredAssistantLanguage();
  const badge = document.getElementById("langBadge");
  badge.textContent = shownLang.toUpperCase();
  badge.className = "lang-badge " + (shownLang !== "en" ? "hi" : "");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// ── Product panel ──────────────────────────────────────────────────────
function renderProducts(products) {
  currentProducts = products;
  const panel = document.getElementById("productsPanel");
  if (!products || products.length === 0) {
    panel.innerHTML = '<div class="empty-state">Results will appear here</div>';
    return;
  }

  panel.innerHTML = "";
  products.forEach((p, i) => {
    const card = document.createElement("div");
    card.className = "product-card";
    card.onclick = () => addToCart(p, i);

    const hasImage = typeof p.image === "string" && p.image.trim().length > 0;
    const hasLink = typeof p.link === "string" && p.link.trim().length > 0;
    const source = (p.source || "").toString().toLowerCase();
    const showSource = source === "amazon" || source === "webscraper";
    const rating = (p.rating || "").toString().trim();

    const nameSafe = escapeHtml(p.name || "Unnamed Product");
    const categorySafe = escapeHtml(p.category || "shopping");
    const imageSafe = escapeHtml(p.image || "");
    const linkSafe = escapeHtml(p.link || "");
    const sourceLabel = source === "amazon" ? "Amazon" : source === "webscraper" ? "Web" : "";

    card.innerHTML = `
      <div class="product-num">${i + 1}</div>
      ${hasImage ? `
        <div class="product-img-wrap">
          <img class="product-img" src="${imageSafe}" alt="${nameSafe}" onerror="this.parentElement.style.display='none'" />
        </div>
      ` : ""}
      <div class="product-info" style="flex:1">
        <h3>${nameSafe}</h3>
        <div class="cat-row">
          <div class="cat">${categorySafe}</div>
          ${rating ? `<div class="rating">${escapeHtml(`⭐ ${rating}`)}</div>` : ""}
          ${showSource ? `<div class="source-badge">${sourceLabel}</div>` : ""}
        </div>
        <div class="product-actions-row">
          <div class="product-price">₹${Number(p.price || 0).toLocaleString("en-IN")}</div>
          ${hasLink ? `<a class="view-link" href="${linkSafe}" target="_blank" rel="noopener" onclick="event.stopPropagation()">View</a>` : ""}
        </div>
      </div>
    `;
    panel.appendChild(card);
  });
}

// ── Cart ───────────────────────────────────────────────────────────────
function addToCart(item, index) {
  // Prevent duplicate
  if (cart.find(c => c.id === item.id)) {
    addBubble(`${item.name} is already in your cart.`, "system");
    return;
  }
  cart.push(item);
  renderCart();
  addBubble(`Added "${item.name}" to your cart!`, "system");
}

function removeFromCart(id) {
  cart = cart.filter(c => c.id !== id);
  renderCart();
}

function renderCart() {
  const panel = document.getElementById("cartPanel");
  const totalEl = document.getElementById("cartTotal");
  const totalAmt = document.getElementById("cartTotalAmount");
  const checkoutBtn = document.getElementById("checkoutBtn");
  const countEl = document.getElementById("cartCount");

  countEl.textContent = `${cart.length} item${cart.length !== 1 ? "s" : ""}`;

  if (cart.length === 0) {
    panel.innerHTML = '<div class="empty-state">Your cart is empty</div>';
    totalEl.style.display = "none";
    checkoutBtn.style.display = "none";
    return;
  }

  panel.innerHTML = "";
  cart.forEach(item => {
    const div = document.createElement("div");
    div.className = "cart-item";
    div.innerHTML = `
      <div class="cart-item-info">
        <div class="name">${item.name}</div>
        <div class="price">₹${item.price.toLocaleString("en-IN")}</div>
      </div>
      <button class="cart-item-remove" onclick="removeFromCart(${item.id})" title="Remove">✕</button>
    `;
    panel.appendChild(div);
  });

  const total = cart.reduce((sum, i) => sum + i.price, 0);
  totalAmt.textContent = `₹${total.toLocaleString("en-IN")}`;
  totalEl.style.display = "flex";
  checkoutBtn.style.display = "block";
}

function clearCart() {
  cart = [];
  renderCart();
}

// ── Order success ──────────────────────────────────────────────────────
function showOrderSuccess(msg) {
  document.getElementById("orderMsg").textContent = msg;
  document.getElementById("orderOverlay").style.display = "flex";
}

function resetOrder() {
  document.getElementById("orderOverlay").style.display = "none";
  clearCart();
  awaitingConfirmation = false;
  conversationHistory = [];
  document.getElementById("chatWindow").innerHTML = "";
  renderProducts([]);
  addBubble("Welcome back! What would you like to shop for?", "assistant");
}

// ── Listening controls ─────────────────────────────────────────────────
function toggleListening() {
  if (isSpeaking) return;
  isListening ? stopListening() : startListening();
}

function startListening() {
  if (!recognition) recognition = setupRecognition();
  if (!recognition) return;
  isListening = true;
  setMicState("listening");
  setDot("listening");
  setStatus("Listening... speak now");
  try { recognition.start(); } catch(e) {}
}

function stopListening() {
  isListening = false;
  setMicState("");
  setDot("");
  setStatus("Processing...");
  try { recognition.stop(); } catch(e) {}
}

// ── Core voice loop ────────────────────────────────────────────────────
async function handleUserInput(text) {
  if (!text.trim()) return;
  addBubble(text, "user");
  conversationHistory.push({ role: "user", text });

  try {
    const res = await fetch(`${BACKEND}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        preferred_language: preferredLanguage,
        history: conversationHistory,
        current_products: currentProducts,
        cart: cart,
        awaiting_confirmation: awaitingConfirmation
      })
    });

    const data = await res.json();
    const { reply, products, intent, language, cart_action } = data;

    // Update language
    setLanguage(language || "en");

    // Add assistant reply to chat
    addBubble(reply, "assistant");
    conversationHistory.push({ role: "assistant", text: reply });

    // Handle products
    if (products && products.length > 0) {
      renderProducts(products);
    } else if (intent === "search") {
      renderProducts([]);
    }

    // Handle cart actions
    if (cart_action) {
      if (cart_action.type === "add" && cart_action.item) {
        addToCart(cart_action.item, null);
      } else if (cart_action.type === "checkout_prompt") {
        awaitingConfirmation = true;
        addBubble('Say "Yes / Haan" to confirm or "No / Nahi" to cancel', "confirm");
      } else if (cart_action.type === "order_placed") {
        awaitingConfirmation = false;
        const total = cart.reduce((s, i) => s + i.price, 0);
        setTimeout(() => showOrderSuccess(`Total ₹${total.toLocaleString("en-IN")} will be collected on delivery.`), 800);
      } else if (cart_action.type === "cancel") {
        awaitingConfirmation = false;
      }
    }

    // Speak the reply via Murf Falcon
    await speakWithMurf(reply, getPreferredAssistantLanguage());

  } catch (err) {
    setStatus("Error: " + err.message);
    setDot("");
    setMicState("");
    console.error(err);
  }
}

// ── Murf Falcon TTS streaming ──────────────────────────────────────────
async function speakWithMurf(text, language = "en") {
  isSpeaking = true;
  setMicState("speaking");
  setDot("speaking");
  setStatus("Speaking...");

  try {
    const activeVoice = getActiveVoiceConfig(language);
    const speechLanguage = activeVoice.language || language;

    if (activeVoice.provider === "browser") {
      await speakWithBrowser(text, speechLanguage);
      return;
    }

    const res = await fetch(`${BACKEND}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        language: speechLanguage,
        voice_id: activeVoice.voiceId,
        voice_style: activeVoice.style
      })
    });

    if (!res.ok) {
      let msg = `TTS request failed (${res.status})`;
      try {
        const err = await res.json();
        msg = err?.details?.error_message || err?.error || msg;
      } catch (_) {}
      throw new Error(msg);
    }

    const contentType = (res.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("audio")) {
      let details = "Provider returned non-audio response";
      try {
        const err = await res.json();
        details = err?.details?.error_message || err?.error || details;
      } catch (_) {}
      throw new Error(details);
    }

    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const reader = res.body.getReader();
    const chunks = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }

    const blob = new Blob(chunks, { type: "audio/mpeg" });
    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);

    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioCtx.destination);
    source.start();

    source.onended = () => {
      isSpeaking = false;
      setMicState("");
      setDot("");
      setStatus("Press mic to speak");
    };

  } catch (err) {
    // Fallback: use browser speech so conversation still works if provider audio fails.
    try {
      await speakWithBrowser(text, language, "Speaking with browser fallback...");
      console.warn("Murf TTS failed, using browser fallback:", err);
      return;
    } catch (_) {
      // Ignore and show original TTS error below.
    }

    isSpeaking = false;
    setMicState("");
    setDot("");
    setStatus("TTS error: " + err.message);
    console.error(err);
  }
}

// ── Text input helpers ─────────────────────────────────────────────────
function sendText(text) {
  handleUserInput(text);
}

function sendTextFromInput() {
  const input = document.getElementById("textInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  handleUserInput(text);
}

// ── Init ───────────────────────────────────────────────────────────────
window.onload = () => {
  onLanguageChange();
  onVoiceChange();
  addBubble(
    "Hi! I'm ShopVoice 🎙️ Tell me what you're looking for — like \"Gift for mom under ₹1500\" or \"Fitness gear\". I understand English and Hindi!",
    "assistant"
  );
  setStatus("Press mic to start");
  renderCart();
};

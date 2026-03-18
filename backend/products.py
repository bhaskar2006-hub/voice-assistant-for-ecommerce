import os
import re
from functools import lru_cache

import httpx
from bs4 import BeautifulSoup


PRODUCTS = [
    {"id": 1, "name": "Wooden Planter Set", "category": "gardening", "price": 799, "tags": ["gardening", "outdoor", "gift", "mom"]},
    {"id": 2, "name": "Herb Growing Kit", "category": "gardening", "price": 1299, "tags": ["gardening", "plants", "gift", "mom", "kitchen"]},
    {"id": 3, "name": "Noise Cancelling Headphones", "category": "electronics", "price": 3499, "tags": ["music", "work", "tech", "gift"]},
    {"id": 4, "name": "Scented Candle Gift Set", "category": "home", "price": 699, "tags": ["gift", "home", "relaxation", "mom"]},
    {"id": 5, "name": "Yoga Mat Premium", "category": "fitness", "price": 1599, "tags": ["fitness", "yoga", "health", "gift"]},
    {"id": 6, "name": "Smart Water Bottle", "category": "fitness", "price": 999, "tags": ["fitness", "health", "tech", "gift"]},
    {"id": 7, "name": "Coffee Maker Deluxe", "category": "kitchen", "price": 2499, "tags": ["kitchen", "coffee", "home", "gift", "mom"]},
    {"id": 8, "name": "Gardening Tool Kit", "category": "gardening", "price": 1849, "tags": ["gardening", "outdoor", "mom", "gift"]},
    {"id": 9, "name": "Silk Pillowcase Set", "category": "bedroom", "price": 1199, "tags": ["home", "sleep", "luxury", "gift", "mom"]},
    {"id": 10, "name": "Bluetooth Speaker Mini", "category": "electronics", "price": 1499, "tags": ["music", "outdoor", "gift", "tech"]},
    {"id": 11, "name": "Terracotta Pot Set", "category": "gardening", "price": 549, "tags": ["gardening", "home", "mom", "gift"]},
    {"id": 12, "name": "Wireless Earbuds", "category": "electronics", "price": 2199, "tags": ["music", "tech", "gift", "fitness"]},
]

SCRAPE_URLS = [
    ("https://webscraper.io/test-sites/e-commerce/static/computers/laptops", "laptops"),
    ("https://webscraper.io/test-sites/e-commerce/static/computers/tablets", "tablets"),
    ("https://webscraper.io/test-sites/e-commerce/static/phones/touch", "phones"),
]

USD_TO_INR = 83.0


def _normalize_tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _parse_price_in_inr(price_text: str, assume_usd: bool = False) -> int:
    text = str(price_text or "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text.replace(",", ""))
    if not match:
        return 0

    value = float(match.group(1))
    lower = text.lower()
    has_usd_hint = "$" in text or "usd" in lower
    has_inr_hint = "₹" in text or "inr" in lower or "rs" in lower

    if assume_usd or (has_usd_hint and not has_inr_hint):
        value *= USD_TO_INR
    return int(round(value))


def _query_from_keywords(keywords: list) -> str:
    return " ".join([k.strip() for k in (keywords or []) if k and k.strip()]).strip()


def _product_id(seed: str) -> int:
    return abs(hash(seed)) % 1000000


def _extract_tags(name: str, extra: str = "") -> list:
    return sorted(list(_normalize_tokens(f"{name} {extra}")))[:12]


def _dedupe_by_name_price(items: list) -> list:
    unique = []
    seen = set()
    for item in items:
        key = (str(item.get("name", "")).strip().lower(), int(item.get("price", 0) or 0))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _scrape_amazon_structured(query: str, max_budget: int = None) -> list:
    api_key = os.getenv("SCRAPERAPI_KEY", "").strip()
    if not api_key or not query:
        return []

    try:
        params = {
            "api_key": api_key,
            "query": query,
            "country_code": "in",
        }
        with httpx.Client(timeout=25.0) as client:
            resp = client.get("https://api.scraperapi.com/structured/amazon/search", params=params)
        if resp.status_code != 200:
            return []

        data = resp.json()
        raw_items = data.get("results") or data.get("shopping_results") or []
        out = []
        for item in raw_items[:20]:
            name = (item.get("name") or item.get("title") or "").strip()
            if not name:
                continue

            price_raw = item.get("price_string") or item.get("price") or item.get("extracted_price") or ""
            price = _parse_price_in_inr(price_raw, assume_usd=False)
            if price <= 0:
                continue
            if max_budget is not None and price > max_budget:
                continue

            category = (query.split()[0].lower() if query.split() else "shopping")
            image = (item.get("image") or item.get("thumbnail") or "").strip()
            link = (item.get("url") or item.get("link") or "").strip()
            rating = str(item.get("stars") or item.get("rating") or "").strip()

            out.append(
                {
                    "id": _product_id(f"amazon-structured:{name}:{price}"),
                    "name": name,
                    "category": category,
                    "price": price,
                    "image": image,
                    "link": link,
                    "rating": rating,
                    "source": "amazon",
                    "tags": _extract_tags(name, query),
                }
            )
        return out
    except Exception:
        return []


def _scrape_amazon_raw_html(query: str, max_budget: int = None) -> list:
    api_key = os.getenv("SCRAPERAPI_KEY", "").strip()
    if not api_key or not query:
        return []

    try:
        search_url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
        proxy_url = f"https://api.scraperapi.com/?api_key={api_key}&url={search_url}&country_code=in"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(proxy_url)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select('[data-component-type="s-search-result"]')
        out = []
        for card in cards[:20]:
            name_el = card.select_one("h2 a span") or card.select_one(".a-size-medium")
            price_el = card.select_one(".a-price .a-offscreen") or card.select_one(".a-price-whole")
            img_el = card.select_one("img.s-image")
            link_el = card.select_one("h2 a")
            rating_el = card.select_one(".a-icon-alt")

            name = (name_el.get_text(strip=True) if name_el else "").strip()
            if not name:
                continue

            price = _parse_price_in_inr(price_el.get_text(strip=True) if price_el else "", assume_usd=False)
            if price <= 0:
                continue
            if max_budget is not None and price > max_budget:
                continue

            image = img_el.get("src", "").strip() if img_el else ""
            href = link_el.get("href", "").strip() if link_el else ""
            link = f"https://www.amazon.in{href}" if href.startswith("/") else href
            rating = (rating_el.get_text(strip=True).split()[0] if rating_el else "").strip()
            category = (query.split()[0].lower() if query.split() else "shopping")

            out.append(
                {
                    "id": _product_id(f"amazon-raw:{name}:{price}"),
                    "name": name,
                    "category": category,
                    "price": price,
                    "image": image,
                    "link": link,
                    "rating": rating,
                    "source": "amazon",
                    "tags": _extract_tags(name, query),
                }
            )
        return out
    except Exception:
        return []


@lru_cache(maxsize=1)
def _scrape_products_from_web() -> list:
    scraped = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ShopVoiceBot/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
        for url, category in SCRAPE_URLS:
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except Exception:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".thumbnail")
            for card in cards:
                title_el = card.select_one(".title")
                price_el = card.select_one(".price")
                desc_el = card.select_one(".description")
                if not title_el or not price_el:
                    continue

                name = (title_el.get("title") or title_el.get_text(strip=True) or "").strip()
                description = (desc_el.get_text(" ", strip=True) if desc_el else "")
                price = _parse_price_in_inr(price_el.get_text(" ", strip=True), assume_usd=True)
                if not name or price <= 0:
                    continue

                tokens = _normalize_tokens(f"{name} {description} {category}")
                tags = sorted(list(tokens))[:12]
                item_id = abs(hash(f"{category}:{name}:{price}")) % 1000000
                scraped.append({
                    "id": item_id,
                    "name": name,
                    "category": category,
                    "price": price,
                    "image": "",
                    "link": "",
                    "rating": "",
                    "source": "webscraper",
                    "tags": tags,
                })

    return scraped


def _normalized_stem(token: str) -> str:
    t = (token or "").strip().lower()
    if len(t) > 3 and t.endswith("s"):
        return t[:-1]
    return t


def _keyword_match_score(keyword: str, token: str) -> int:
    kw = _normalized_stem(keyword)
    tk = _normalized_stem(token)
    if not kw or not tk:
        return 0
    if kw == tk:
        return 3
    if kw in tk or tk in kw:
        return 1
    return 0


def _score_product(product: dict, keywords: list) -> int:
    if not keywords:
        return 1

    haystack = _normalize_tokens(
        f"{product.get('name', '')} {product.get('category', '')} {' '.join(product.get('tags', []))}"
    )
    total = 0
    for kw in keywords:
        best = 0
        for token in haystack:
            best = max(best, _keyword_match_score(kw, token))
            if best == 3:
                break
        total += best
    return total


def search_products(keywords: list, max_budget: int = None, limit: int = 3) -> list:
    query = _query_from_keywords(keywords)
    all_candidates = []

    # Stage 1: ScraperAPI live Amazon results (if key is configured).
    if query and os.getenv("SCRAPERAPI_KEY", "").strip():
        amazon_structured = _scrape_amazon_structured(query, max_budget)
        amazon_raw = [] if amazon_structured else _scrape_amazon_raw_html(query, max_budget)
        all_candidates.extend(amazon_structured + amazon_raw)

    # Stage 2: Public webscraper test-site live results.
    all_candidates.extend(_scrape_products_from_web())

    # Stage 3: Local catalog as guaranteed fallback.
    for local in PRODUCTS:
        p = dict(local)
        p.setdefault("image", "")
        p.setdefault("link", "")
        p.setdefault("rating", "")
        p.setdefault("source", "local")
        all_candidates.append(p)

    all_candidates = _dedupe_by_name_price(all_candidates)
    scored = []

    for p in all_candidates:
        score = _score_product(p, keywords)
        if score <= 0:
            continue
        if max_budget is not None and p["price"] > max_budget:
            continue
        scored.append((score, p))

    # If keyword matching finds nothing, still return budget-compatible options.
    if not scored:
        for p in all_candidates:
            if max_budget is not None and p["price"] > max_budget:
                continue
            scored.append((0, p))

    scored.sort(key=lambda x: (-x[0], x[1]["price"]))

    unique = []
    seen = set()
    for _, item in scored:
        key = (str(item.get("name", "")).strip().lower(), int(item.get("price", 0) or 0))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def get_product_by_index(index: int, products: list) -> dict:
    if 0 <= index < len(products):
        return products[index]
    return None

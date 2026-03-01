"""
Pros/cons extraction from shoe review text.

Tier 1: Claude haiku  (best — understands context, shoe-specific)
Tier 2: HuggingFace Inference API text generation (good — LLM without Anthropic key)
Tier 3: Keyword-based extraction (always works, no API dependency)
"""
import re
import os
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Tier 1: Claude-based extraction
# ---------------------------------------------------------------------------

def extract_pros_cons_claude(review_text: str, shoe_model: str = "") -> dict:
    """Use Claude to extract shoe-specific pros and cons with full context awareness."""
    if not review_text or len(review_text.strip()) < 30:
        return {"pros": [], "cons": []}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        shoe_context = f" about the {shoe_model}" if shoe_model else ""
        prompt = (
            f"Extract the specific pros and cons from this running shoe review{shoe_context}.\n\n"
            f"Review:\n\"\"\"\n{review_text[:2000]}\n\"\"\"\n\n"
            "Return ONLY valid JSON in this exact format:\n"
            "{\"pros\": [\"phrase 1\", \"phrase 2\"], \"cons\": [\"phrase 1\"]}\n\n"
            "Rules:\n"
            "- Each pro/con must be 3-9 words, capturing a SPECIFIC point about this shoe\n"
            "- Only include things the person directly experienced\n"
            "- Do NOT include vague phrases like 'good shoe' or 'liked it'\n"
            "- Max 5 pros, max 5 cons\n"
            "- If a point is ambiguous (positive sentence with a negative keyword), "
            "  read carefully and classify correctly\n"
            "- Empty arrays are fine if there are no clear pros or cons"
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return {
            "pros": [str(p) for p in data.get("pros", [])[:5]],
            "cons": [str(c) for c in data.get("cons", [])[:5]],
        }
    except Exception as e:
        print(f"Claude pros/cons extraction failed: {e} — trying HF fallback")
        return extract_pros_cons_hf(review_text, shoe_model)


# ---------------------------------------------------------------------------
# Tier 2: HuggingFace Inference API (LLM fallback)
# ---------------------------------------------------------------------------

def extract_pros_cons_hf(review_text: str, shoe_model: str = "") -> dict:
    """Use HuggingFace Inference API (chat_completion) to extract pros and cons."""
    if not review_text or len(review_text.strip()) < 30:
        return {"pros": [], "cons": []}
    try:
        from huggingface_hub import InferenceClient  # type: ignore
        token = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN")
        if not token:
            return extract_pros_cons_keywords(review_text)

        client = InferenceClient(provider="hf-inference", api_key=token, timeout=30.0)
        shoe_context = f" about the {shoe_model}" if shoe_model else ""
        prompt = (
            f"Extract specific pros and cons from this running shoe review{shoe_context}.\n\n"
            f"Review:\n\"\"\"\n{review_text[:1500]}\n\"\"\"\n\n"
            "Return ONLY valid JSON:\n"
            "{\"pros\": [\"specific phrase\"], \"cons\": [\"specific phrase\"]}\n\n"
            "Rules: each item 3-9 words, max 5 each, only direct experiences, "
            "no vague phrases. Return ONLY the JSON."
        )
        response = client.chat_completion(
            model="mistralai/Mistral-7B-Instruct-v0.3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        # Find first JSON object in response
        json_match = re.search(r'\{[\s\S]*?"pros"[\s\S]*?\}', raw)
        if json_match:
            raw = json_match.group()
        data = json.loads(raw)
        return {
            "pros": [str(p) for p in data.get("pros", [])[:5]],
            "cons": [str(c) for c in data.get("cons", [])[:5]],
        }
    except Exception as e:
        print(f"HF pros/cons extraction failed: {e} — using keyword fallback")
        return extract_pros_cons_keywords(review_text)


# ---------------------------------------------------------------------------
# Tier 3: Keyword-based fallback (no API dependency)
# ---------------------------------------------------------------------------

_POSITIVE_KEYWORDS = [
    "comfortable", "comfy", "cushioned", "cushioning", "soft", "plush",
    "responsive", "bouncy", "springy", "durable", "long-lasting", "sturdy",
    "well-built", "quality", "solid", "lightweight", "light", "breathable",
    "ventilated", "airy", "great", "excellent", "amazing", "fantastic",
    "love", "perfect", "grip", "traction", "stable", "support", "supportive",
    "fits well", "true to size", "roomy", "flexible", "fast", "snappy",
    "energy return", "protective",
]

_NEGATIVE_KEYWORDS = [
    "uncomfortable", "hard", "stiff", "rigid", "pain", "hurts", "sore",
    "wears out", "worn out", "breaks", "tears", "falls apart", "heavy", "bulky",
    "clunky", "terrible", "awful", "disappointed", "poor", "worst",
    "slippery", "no grip", "poor traction", "unstable",
    "narrow", "too narrow", "runs narrow",
    "wide", "too wide", "too loose",
    "tight", "too tight", "too small", "too big",
    "runs small", "runs large", "blister", "hot spot",
    "short", "long", "creasing",
]


def extract_pros_cons_keywords(review_text: str) -> dict:
    """Keyword-based fallback — less accurate but no API dependency."""
    if not review_text or not review_text.strip():
        return {"pros": [], "cons": []}

    sentences = re.split(r"[.!?\n]+", review_text)
    pros, cons = [], []

    for sentence in sentences:
        s = sentence.strip()
        sl = s.lower()
        if len(sl) < 15:
            continue

        is_negated = bool(re.search(r"\b(not|never|no|don't|doesn't|didn't|wasn't|isn't|aren't)\b", sl))

        pos_kw_match = None
        for kw in _POSITIVE_KEYWORDS:
            m = re.search(r"\b" + re.escape(kw) + r"\b", sl)
            if m:
                pos_kw_match = (kw, m.start())
                break

        neg_kw_match = None
        for kw in _NEGATIVE_KEYWORDS:
            m = re.search(r"\b" + re.escape(kw) + r"\b", sl)
            if m:
                neg_kw_match = (kw, m.start())
                break

        def _extract_around(kw: str, idx: int) -> str:
            """Grab roughly 10 words centred on the keyword."""
            start = max(0, idx - 25)
            end = min(len(s), idx + len(kw) + 55)
            snippet = s[start:end].strip()
            snippet = re.sub(r"^[^a-zA-Z]+", "", snippet)
            words = snippet.split()[:10]
            return " ".join(words)

        if pos_kw_match and not is_negated:
            phrase = _extract_around(*pos_kw_match)
            if phrase and phrase not in pros:
                pros.append(phrase)
        elif neg_kw_match and not is_negated:
            phrase = _extract_around(*neg_kw_match)
            if phrase and phrase not in cons:
                cons.append(phrase)
        elif pos_kw_match and is_negated:
            # negated positive → con
            phrase = _extract_around(*pos_kw_match)
            if phrase and phrase not in cons:
                cons.append(phrase)

        # Catch sentences with BOTH pos and neg keywords
        if pos_kw_match and neg_kw_match and not is_negated:
            neg_phrase = _extract_around(*neg_kw_match)
            if neg_phrase and neg_phrase not in cons:
                cons.append(neg_phrase)

    return {
        "pros": list(dict.fromkeys(pros))[:5],
        "cons": list(dict.fromkeys(cons))[:5],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pros_cons(review_text: str, shoe_model: str = "") -> dict:
    """
    Extract pros and cons from a review.
    Tier 1: Claude (ANTHROPIC_API_KEY)
    Tier 2: HuggingFace LLM (HUGGINGFACE_API_KEY / HF_TOKEN)
    Tier 3: Keyword matching (always available)
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return extract_pros_cons_claude(review_text, shoe_model)
    if os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN"):
        return extract_pros_cons_hf(review_text, shoe_model)
    return extract_pros_cons_keywords(review_text)

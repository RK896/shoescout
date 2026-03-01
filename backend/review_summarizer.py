"""
Review summarization for shoe reviews.

Tier 1: Claude haiku  (best — specific, shoe-aware)
Tier 2: HuggingFace Inference API text generation (LLM without Anthropic key)
Tier 3: Simple extractive summary (always works, no API dependency)
"""
import re
import os
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Tier 1: Claude-based summarization
# ---------------------------------------------------------------------------

def generate_summary_claude(review_text: str, shoe_model: str = "") -> str:
    """Use Claude to write a clean 1-2 sentence summary of the review."""
    if not review_text or len(review_text.strip()) < 30:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        shoe_context = f" of the {shoe_model}" if shoe_model else ""
        prompt = (
            f"Summarize this running shoe review{shoe_context} in 1-2 clear sentences.\n\n"
            f"Review:\n\"\"\"\n{review_text[:1500]}\n\"\"\"\n\n"
            "Rules:\n"
            "- Write from the reviewer's perspective (e.g. 'The reviewer found…' or direct)\n"
            "- Be specific — mention actual points raised (comfort, fit, durability, etc.)\n"
            "- Do NOT add opinions of your own\n"
            "- Keep it under 200 characters\n"
            "- Return only the summary, no preamble"
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = response.content[0].text.strip()
        summary = summary.strip('"').strip("'")
        return summary[:500]
    except Exception as e:
        print(f"Claude summarization failed: {e} — trying HF fallback")
        return generate_summary_hf(review_text, shoe_model)


# ---------------------------------------------------------------------------
# Tier 2: HuggingFace Inference API (LLM fallback)
# ---------------------------------------------------------------------------

def generate_summary_hf(review_text: str, shoe_model: str = "") -> str:
    """Use HuggingFace Inference API to generate a summary."""
    if not review_text or len(review_text.strip()) < 30:
        return ""
    try:
        from huggingface_hub import InferenceClient  # type: ignore
        token = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN")
        if not token:
            return generate_summary_simple(review_text)

        client = InferenceClient(provider="hf-inference", api_key=token, timeout=30.0)
        shoe_context = f" of the {shoe_model}" if shoe_model else ""
        prompt = (
            f"Summarize this running shoe review{shoe_context} in 1-2 sentences. "
            "Be specific about comfort, fit, and durability. "
            "Return only the summary, no preamble.\n\n"
            f"Review:\n\"\"\"\n{review_text[:1000]}\n\"\"\""
        )
        response = client.chat_completion(
            model="mistralai/Mistral-7B-Instruct-v0.3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.2,
        )
        summary = response.choices[0].message.content.strip()
        summary = summary.strip('"').strip("'")
        return summary[:500]
    except Exception as e:
        print(f"HF summarization failed: {e} — using simple fallback")
        return generate_summary_simple(review_text)


# ---------------------------------------------------------------------------
# Tier 3: Simple extractive fallback
# ---------------------------------------------------------------------------

def generate_summary_simple(review_text: str, max_length: int = 200) -> str:
    """Extract the most informative sentence as a fallback summary."""
    if not review_text or not review_text.strip():
        return ""

    text = " ".join(review_text.split())
    if len(text) <= max_length:
        return text

    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 25]
    if not sentences:
        words = text[:max_length].rsplit(" ", 1)[0]
        return words + "…"

    summary = sentences[0]
    if len(summary) > max_length:
        words = summary[:max_length].rsplit(" ", 1)[0]
        return words + "…"
    return summary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_summary(review_text: str, shoe_model: str = "") -> str:
    """
    Generate a summary of a shoe review.
    Tier 1: Claude (ANTHROPIC_API_KEY)
    Tier 2: HuggingFace LLM (HUGGINGFACE_API_KEY / HF_TOKEN)
    Tier 3: Simple extractive summary (always available)
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return generate_summary_claude(review_text, shoe_model)
    if os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN"):
        return generate_summary_hf(review_text, shoe_model)
    return generate_summary_simple(review_text)

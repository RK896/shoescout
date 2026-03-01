import os
import re


def format_shoes_for_context(shoes_with_reviews: list) -> str:
    """Format shoe data and reviews as readable context for Claude."""
    lines = []
    for shoe in shoes_with_reviews:
        model = shoe.get("model", "Unknown")
        brand = shoe.get("brand", "Unknown")
        retailers = shoe.get("retailers", [])

        price_strs = []
        for r in retailers:
            price_strs.append(f"{r['retailer']}: {r['price']}")
        prices = " | ".join(price_strs) if price_strs else "Price unknown"

        lines.append(f"SHOE: {brand} {model}")
        lines.append(f"  Prices: {prices}")

        reviews = shoe.get("reviews", [])
        if reviews:
            for i, rev in enumerate(reviews[:3]):
                summary = rev.get("summary", "")
                pros = rev.get("pros", [])[:3]
                cons = rev.get("cons", [])[:3]
                if summary:
                    lines.append(f"  Community review {i+1}: {summary}")
                if pros:
                    lines.append(f"  Pros: {', '.join(pros)}")
                if cons:
                    lines.append(f"  Cons: {', '.join(cons)}")
        lines.append("")

    return "\n".join(lines)


SYSTEM_PROMPT = """You are ShoeScout AI, a friendly and knowledgeable running shoe expert assistant.

You have access to real-time price data and Reddit community reviews for running shoes in our database. Your job is to help users find the perfect running shoe.

Guidelines:
- Give specific, actionable recommendations based on the user's needs
- Always mention specific model names when recommending shoes
- Include price information when relevant
- Reference community pros/cons from the real reviews in the database
- If the user describes specific needs (marathon training, trail running, wide feet, overpronation, budget), tailor your advice accordingly
- Be concise but thorough — 2-4 short paragraphs
- If a user's question is completely unrelated to shoes, politely redirect them
- Format your response clearly with line breaks for readability
- If available data is limited for a specific need, give your best honest advice"""


def get_shoe_recommendation(message: str, shoes_with_reviews: list) -> str:
    """Get shoe recommendation from Claude based on user message and shoe data."""
    try:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return (
                "AI recommendations are temporarily unavailable. "
                "Try searching for shoes using the search bar above!"
            )

        client = anthropic.Anthropic(api_key=api_key)

        shoe_context = format_shoes_for_context(shoes_with_reviews)
        if not shoe_context.strip():
            shoe_context = "No matching shoes found in the database for this query."

        user_content = (
            f"Shoe database (most relevant matches for the user's question):\n\n"
            f"{shoe_context}\n"
            f"---\n"
            f"User question: {message}"
        )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        return response.content[0].text

    except ImportError:
        return "AI recommendations require the 'anthropic' package. Please install it."
    except Exception as e:
        print(f"Chat error: {e}")
        return "Sorry, I couldn't generate a recommendation right now. Please try again in a moment."

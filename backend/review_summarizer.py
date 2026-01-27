import re
import os
from dotenv import load_dotenv

load_dotenv()

# Try to import OpenAI, fallback to simple summary if not available
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = OpenAI(api_key=api_key)
        print("OpenAI client initialized successfully")
    else:
        client = None
        print("Warning: OPENAI_API_KEY not found in environment. Using simple summaries.")
except ImportError:
    OPENAI_AVAILABLE = False
    client = None
    print("Warning: OpenAI package not installed. Using simple summaries.")

def generate_summary_llm(review_text):
    """Generate summary using OpenAI LLM"""
    if not client or not review_text or len(review_text.strip()) == 0:
        return None
    
    try:
        # Truncate if too long (OpenAI has token limits)
        text = review_text[:2000] if len(review_text) > 2000 else review_text
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use cheaper model for summaries
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that summarizes product reviews. Create a concise 1-2 sentence summary highlighting the key points about the product."
                },
                {
                    "role": "user",
                    "content": f"Summarize this review in 1-2 sentences:\n\n{text}"
                }
            ],
            max_tokens=100,
            temperature=0.3
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating LLM summary: {e}")
        return None

def generate_summary_simple(review_text, max_length=150):
    """
    Generate a simple extractive summary of a review (fallback).
    Extracts the first meaningful sentence or key phrases.
    """
    if not review_text or len(review_text.strip()) == 0:
        return "No review text available."
    
    # Remove extra whitespace
    text = ' '.join(review_text.split())
    
    # If text is short enough, return as is
    if len(text) <= max_length:
        return text
    
    # Try to find the first sentence that's meaningful
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]  # Filter out very short fragments
    
    if sentences:
        # Return first meaningful sentence, truncated if needed
        summary = sentences[0]
        if len(summary) > max_length:
            # Truncate at word boundary
            words = summary[:max_length].rsplit(' ', 1)[0]
            summary = words + "..."
        return summary
    
    # Fallback: just truncate the text
    return text[:max_length].rsplit(' ', 1)[0] + "..."

def generate_summary(review_text, max_length=150):
    """
    Generate summary using LLM if available, otherwise use simple extraction.
    """
    # Try LLM first
    if OPENAI_AVAILABLE and client:
        print(f"Attempting LLM summary for text length: {len(review_text)}")
        llm_summary = generate_summary_llm(review_text)
        if llm_summary:
            print(f"LLM summary generated: {llm_summary[:50]}...")
            return llm_summary
        else:
            print("LLM summary failed, using simple summary")
    else:
        if not OPENAI_AVAILABLE:
            print("OpenAI not available, using simple summary")
        elif not client:
            print("OpenAI client not initialized, using simple summary")
    
    # Fallback to simple summary
    return generate_summary_simple(review_text, max_length)

import re
import os
from dotenv import load_dotenv

load_dotenv()

def generate_summary_llm(review_text):
    """Generate summary using Hugging Face Inference API (free tier)"""
    if not review_text or len(review_text.strip()) == 0:
        return None
    
    try:
        from huggingface_hub import InferenceClient  # type: ignore
        
        # Truncate if too long (HF models have token limits)
        text = review_text[:1024] if len(review_text) > 1024 else review_text
        
        # Get API key (optional but recommended for higher rate limits)
        HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN")
        
        # Initialize client - works without key but with lower rate limits
        if HF_TOKEN:
            client = InferenceClient(
                provider="hf-inference",
                api_key=HF_TOKEN,
                timeout=15.0,  # 15 second timeout
            )
        else:
            # Try without key (may have rate limits)
            client = InferenceClient(
                provider="hf-inference",
                timeout=15.0,  # 15 second timeout
            )
        
        print(f"Calling Hugging Face API for summary...")
        result = client.summarization(
            text,
            model="facebook/bart-large-cnn",
        )
        
        if result:
            # Extract summary text from SummarizationOutput object
            if hasattr(result, 'summary_text'):
                summary = result.summary_text.strip()
            elif hasattr(result, 'text'):
                summary = result.text.strip()
            elif isinstance(result, str):
                summary = result.strip()
            else:
                # Try converting to string
                summary = str(result).strip()
            
            if summary:
                print(f"HF summary generated: {summary[:50]}...")
                return summary
        
        return None
    except ImportError:
        print("huggingface_hub not installed, falling back to simple summary")
        return None
    except TimeoutError:
        print("HF API call timed out, falling back to simple summary")
        return None
    except Exception as e:
        # Check if it's a timeout/504 error
        error_str = str(e)
        if "504" in error_str or "timeout" in error_str.lower() or "Gateway Time-out" in error_str:
            print("HF API timeout/504 error, falling back to simple summary")
        else:
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
    Generate summary using Hugging Face LLM if available, otherwise use simple extraction.
    """
    # Try LLM first (Hugging Face - free tier)
    llm_summary = generate_summary_llm(review_text)
    if llm_summary:
        return llm_summary
    
    # Fallback to simple summary
    print("Using simple summary fallback")
    return generate_summary_simple(review_text, max_length)

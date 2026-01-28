import re
import os
from dotenv import load_dotenv

load_dotenv()

def extract_pros_cons_llm(review_text):
    """Extract pros and cons using Hugging Face Inference API (optional enhancement)"""
    # For now, skip LLM extraction due to complexity and reliability issues
    # We'll use keyword-based extraction as primary method
    return {"pros": [], "cons": []}

def extract_pros_cons_keywords(review_text):
    """Extract pros and cons using keyword-based approach"""
    if not review_text or len(review_text.strip()) == 0:
        return {"pros": [], "cons": []}
    
    # Common positive and negative keywords/phrases for shoes
    positive_keywords = [
        'comfortable', 'comfy', 'cushioned', 'cushioning', 'soft', 'plush', 
        'responsive', 'bouncy', 'springy', 'durable', 'long-lasting', 'sturdy',
        'well-built', 'quality', 'solid', 'lightweight', 'light', 'breathable',
        'ventilated', 'airy', 'good', 'great', 'excellent', 'amazing', 'fantastic',
        'love', 'perfect', 'grip', 'traction', 'stable', 'support', 'supportive',
        'fits well', 'true to size', 'roomy', 'flexible'
    ]
    
    negative_keywords = [
        'uncomfortable', 'hard', 'stiff', 'rigid', 'pain', 'hurts', 'sore',
        'wears out', 'worn', 'breaks', 'tears', 'falls apart', 'heavy', 'bulky',
        'clunky', 'bad', 'terrible', 'awful', 'hate', 'disappointed', 'poor',
        'worst', 'slippery', 'no grip', 'poor traction', 'unstable', 'too narrow',
        'too wide', 'too tight', 'too loose', 'too small', 'too big', 'runs small',
        'runs large', 'runs narrow', 'runs wide'
    ]
    
    text_lower = review_text.lower()
    pros = []
    cons = []
    
    # Split into sentences
    sentences = re.split(r'[.!?]+', review_text)
    
    for sentence in sentences:
        sentence_clean = sentence.strip()
        sentence_lower = sentence_clean.lower()
        
        if len(sentence_lower) < 10:
            continue
        
        # Check for positive keywords
        found_positive = False
        for keyword in positive_keywords:
            if keyword in sentence_lower:
                # Extract a concise phrase (up to 12 words)
                words = sentence_clean.split()[:12]
                phrase = ' '.join(words).strip()
                # Clean up phrase
                phrase = re.sub(r'^[^a-zA-Z]*', '', phrase)  # Remove leading punctuation
                if phrase and len(phrase) < 100 and phrase not in pros:
                    pros.append(phrase)
                    found_positive = True
                    break
        
        # Check for negative keywords (only if no positive found in same sentence)
        if not found_positive:
            for keyword in negative_keywords:
                if keyword in sentence_lower:
                    words = sentence_clean.split()[:12]
                    phrase = ' '.join(words).strip()
                    phrase = re.sub(r'^[^a-zA-Z]*', '', phrase)
                    if phrase and len(phrase) < 100 and phrase not in cons:
                        cons.append(phrase)
                        break
    
    # Remove duplicates and limit
    pros = list(dict.fromkeys(pros))[:5]  # Preserve order, limit to 5
    cons = list(dict.fromkeys(cons))[:5]
    
    return {"pros": pros, "cons": cons}

def extract_pros_cons(review_text):
    """
    Extract pros and cons from a review using keyword-based extraction.
    """
    return extract_pros_cons_keywords(review_text)

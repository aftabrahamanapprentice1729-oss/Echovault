import os
import json
import re
from groq import Groq

# 🚨 PASTE YOUR GROQ API KEY HERE 🚨
GROQ_API_KEY = "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" 

client = Groq(api_key=GROQ_API_KEY)

def get_smart_tags(title, description=""):
    """
    Asks the Cloud Llama 3 AI (via Groq) to analyze the content 
    and returns exactly 2 Netflix-style genre tags.
    """
    if not title:
        return ["Audiobook"]

    safe_desc = description[:1000] if description else "No description provided."

    prompt = f"""
    You are a strict and highly accurate Netflix-style content curator.
    Analyze the following audio story based on its Title and Description.
    
    Title: {title}
    Description: {safe_desc}
    
    Choose 1 or 2 most accurate genres from this EXACT list:
    Sci-Fi, Mystery, Horror, Fantasy, Thriller, Romance, Comedy, History, True Crime, Action, Podcast, Classic Literature, Non-Fiction, Biography, Adventure, Supernatural, Psychological, Crime.
    
    STRICT RULES FOR CREDIT ROLLS:
    1. The description is often just a list of cast and crew. IGNORE technical audio/video words.
    2. Look closely at the AUTHOR, TITLE, and CHARACTER NAMES.
    3. If you see titles like "Inspector", "Detective", "Sherlock"  or famous literary sleuths (Jayanta, Manik, Byomkesh, Holmes,Feluda ), tag it as "Mystery" or "Adventure".
    4. If the title implies monsters, ghosts, or nightmares, tag it as "Adventure", "Supernatural", or "Horror".
    5. Respond ONLY with a valid JSON array of strings. Do not write any other words.
    Example: ["Mystery", "Adventure"]
    """

    try:
        # Calling the lightning-fast Llama 3 8B model on Groq's servers
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama3-8b-8192",
            temperature=0.1,
        )
        
        raw_text = chat_completion.choices[0].message.content
        
        # Strip out any markdown formatting the AI might add
        clean_text = raw_text.replace('```json', '').replace('```', '').strip()
        
        # Extract just the JSON array
        match = re.search(r'\[.*\]', clean_text, re.DOTALL)
        if match:
            clean_text = match.group(0)
            
        tags = json.loads(clean_text)
        
        if isinstance(tags, list):
            return tags[:2]
        return ["Audiobook"]
        
    except Exception as e:
        print(f"Cloud AI Labeling Error: {e}")
        return ["Unlabelled"]

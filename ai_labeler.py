import ollama
import json
import re

def get_smart_tags(title, description=""):
    """
    Takes a title and description, asks your LOCAL Ollama AI to analyze the content, 
    and returns a list of exactly 2 Netflix-style genre tags.
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
    1. The description is often just a list of cast and crew (Director, Studio, Sound Design, Starring). IGNORE technical audio/video words.
    2. Look closely at the AUTHOR, TITLE, and CHARACTER NAMES in the cast list.
    3. If you see titles like "Inspector", "Detective", or famous literary sleuths/adventurers (e.g., Jayanta, Manik, Byomkesh, Holmes), tag it as "Mystery" or "Adventure".
    4. If the title implies monsters, ghosts, or nightmares (e.g., "Dragon-er Duswapna"), tag it as "Adventure", "Supernatural", or "Horror".
    5. DO NOT tag "Sci-Fi" unless it explicitly mentions space, aliens, or futuristic tech.
    6. Respond ONLY with a valid JSON array of strings. Do not write any other words.
    Example: ["Mystery", "Adventure"]
    """

    try:
        # Send the prompt to your local Ollama instance
        # Switched to the smarter 'llama3' and added temperature=0.1 to stop random guessing
        response = ollama.generate(
            model='llama3', 
            prompt=prompt,
            options={'temperature': 0.1}
        )
        
        raw_text = response['response']
        
        # Strip out any markdown formatting the AI might add
        clean_text = raw_text.replace('```json', '').replace('```', '').strip()
        
        # Use regex to extract just the JSON array brackets [...]
        match = re.search(r'\[.*\]', clean_text, re.DOTALL)
        if match:
            clean_text = match.group(0)
            
        tags = json.loads(clean_text)
        
        if isinstance(tags, list):
            return tags[:2]
        return ["Audiobook"]
        
    except Exception as e:
        print(f"Ollama AI Labeling Error: {e}")
        return ["Audiobook"] # Fallback if Ollama isn't running
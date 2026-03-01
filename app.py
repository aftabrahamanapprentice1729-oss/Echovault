import json
from ai_labeler import get_smart_tags
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import re
import jwt
import datetime
import yt_dlp 
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'sherlock_super_secret_key_123'

# --- Database Setup & Seamless Upgrades ---
def init_db():
    conn = sqlite3.connect('echovault.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stories (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, yt_id TEXT NOT NULL, cover TEXT NOT NULL, rating REAL DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS favorites (user_id INTEGER, story_id INTEGER, UNIQUE(user_id, story_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, story_id INTEGER, played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_position REAL DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ratings (user_id INTEGER, story_id INTEGER, stars INTEGER, UNIQUE(user_id, story_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, story_id INTEGER, review_text TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS folders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS folder_items (folder_id INTEGER, story_id INTEGER, UNIQUE(folder_id, story_id))''')
    
    # UPGRADES: Safely add new columns if they don't exist yet
    try: cursor.execute('ALTER TABLE history ADD COLUMN last_position REAL DEFAULT 0')
    except sqlite3.OperationalError: pass 
    
    try: cursor.execute('ALTER TABLE stories ADD COLUMN uploader TEXT DEFAULT "Community Upload"')
    except sqlite3.OperationalError: pass 

    # NEW: Add Tags column to store the AI labels
    try: cursor.execute('ALTER TABLE stories ADD COLUMN tags TEXT DEFAULT \'["Audiobook"]\'')
    except sqlite3.OperationalError: pass 

    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect('echovault.db')
    conn.row_factory = sqlite3.Row
    return conn

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers: token = request.headers['Authorization'].split(" ")[1]
        if not token: return jsonify({'error': 'Token missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user_id = data['user_id']
        except Exception: return jsonify({'error': 'Token invalid!'}), 401
        return f(current_user_id, *args, **kwargs)
    return decorated

# --- AUTH ENDPOINTS ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    email, password = data.get('email'), data.get('password')
    if not email or not password: return jsonify({'error': 'Missing data'}), 400
    hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)', (email, hashed_pw))
        conn.commit()
    except sqlite3.IntegrityError: return jsonify({'error': 'Email exists!'}), 409
    finally: conn.close()
    return jsonify({'message': 'Registered!'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (data.get('email'),)).fetchone()
    conn.close()
    if not user or not check_password_hash(user['password_hash'], data.get('password')):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = jwt.encode({'user_id': user['id'], 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)}, app.config['SECRET_KEY'], algorithm='HS256')
    return jsonify({'token': token})
@app.route('/api/search/youtube', methods=['GET'])
@token_required
def search_youtube(current_user_id):
    query = request.args.get('q')
    if not query: return jsonify({"error": "No query provided"}), 400
    
    # extract_flat is True here so the search is lighting fast (under 1 second)
    ydl_opts = {'extract_flat': True, 'quiet': True}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 'ytsearch5:' tells yt-dlp to just search YouTube and grab the top 5 results
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            results = []
            
            if 'entries' in info:
                for entry in info['entries']:
                    yt_id = entry.get('id')
                    results.append({
                        'yt_id': yt_id,
                        'title': entry.get('title'),
                        'uploader': entry.get('uploader') or entry.get('channel') or 'YouTube',
                        'cover': f"https://img.youtube.com/vi/{yt_id}/maxresdefault.jpg"
                    })
            return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": "Search failed"}), 500
# --- STORY ENDPOINTS (UPGRADED WITH LOCAL AI) ---
@app.route('/api/stories', methods=['GET'])
@token_required
def get_stories(current_user_id):
    conn = get_db_connection()
    query = '''SELECT s.*, CASE WHEN f.user_id IS NOT NULL THEN 1 ELSE 0 END as is_favorited, IFNULL((SELECT stars FROM ratings WHERE user_id = ? AND story_id = s.id), 0) as my_rating FROM stories s LEFT JOIN favorites f ON s.id = f.story_id AND f.user_id = ? ORDER BY s.id DESC'''
    stories = conn.execute(query, (current_user_id, current_user_id)).fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in stories])

@app.route('/api/stories', methods=['POST'])
@token_required
def add_story(current_user_id):
    data = request.json
    yt_url = data.get('url')
    
    # Extract_flat set to False so we can grab the YouTube description for the AI
    ydl_opts = {'quiet': True, 'extract_flat': False}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(yt_url, download=False)
            yt_id = info.get('id')
            if not yt_id: return jsonify({"error": "Invalid URL"}), 400
            
            conn = get_db_connection()
            existing = conn.execute('SELECT title FROM stories WHERE yt_id = ?', (yt_id,)).fetchone()
            if existing:
                conn.close()
                return jsonify({"message": f"Already in library: {existing['title']}"}), 200
            
            title = info.get('title', 'Unknown Audio Story')
            uploader = info.get('uploader') or info.get('channel') or 'Community Upload'
            description = info.get('description', '')
            cover_url = f"https://img.youtube.com/vi/{yt_id}/maxresdefault.jpg"
            
            # 🧠 RUN THE LOCAL OLLAMA AI PIPELINE 🧠
            ai_tags = get_smart_tags(title, description)
            tags_json = json.dumps(ai_tags) 
            
            conn.execute('INSERT INTO stories (title, yt_id, cover, rating, uploader, tags) VALUES (?, ?, ?, ?, ?, ?)', 
                         (title, yt_id, cover_url, 0, uploader, tags_json))
            conn.commit()
            conn.close()
            return jsonify({"message": f"Added: {title}"}), 201
    except Exception as e:
        return jsonify({"error": "Failed to extract video data"}), 400

@app.route('/api/stories/<int:story_id>', methods=['DELETE'])
@token_required
def delete_story(current_user_id, story_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM favorites WHERE story_id = ?', (story_id,))
    conn.execute('DELETE FROM history WHERE story_id = ?', (story_id,))
    conn.execute('DELETE FROM ratings WHERE story_id = ?', (story_id,))
    conn.execute('DELETE FROM reviews WHERE story_id = ?', (story_id,))
    conn.execute('DELETE FROM folder_items WHERE story_id = ?', (story_id,))
    conn.execute('DELETE FROM stories WHERE id = ?', (story_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Story deleted from library."})

@app.route('/api/playlist', methods=['POST'])
@token_required
def add_playlist(current_user_id):
    data = request.json
    playlist_url = data.get('url')
    if not playlist_url or 'list=' not in playlist_url: return jsonify({"error": "Not a valid playlist URL"}), 400
    ydl_opts = {'extract_flat': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            if 'entries' not in info: return jsonify({"error": "No videos found in playlist"}), 400
            conn = get_db_connection()
            cursor = conn.cursor()
            added_count, skipped_count = 0, 0
            for entry in info['entries']:
                yt_id = entry.get('id')
                title = entry.get('title')
                uploader = entry.get('uploader') or entry.get('channel') or 'Community Upload' 
                
                if yt_id and title and "[Private video]" not in title and "[Deleted video]" not in title:
                    existing = cursor.execute('SELECT id FROM stories WHERE yt_id = ?', (yt_id,)).fetchone()
                    if not existing:
                        cover_url = f"https://img.youtube.com/vi/{yt_id}/maxresdefault.jpg"
                        
                        # 🧠 RUN LOCAL AI (Title only for playlists to keep extraction fast) 🧠
                        ai_tags = get_smart_tags(title, "")
                        tags_json = json.dumps(ai_tags)
                        
                        cursor.execute('INSERT INTO stories (title, yt_id, cover, rating, uploader, tags) VALUES (?, ?, ?, ?, ?, ?)', 
                                       (title, yt_id, cover_url, 0, uploader, tags_json))
                        added_count += 1
                    else: skipped_count += 1
            conn.commit()
            conn.close()
            msg = f"Extracted {added_count} new stories."
            if skipped_count > 0: msg += f" (Skipped {skipped_count} duplicates)"
            return jsonify({"message": msg}), 201
    except Exception as e: return jsonify({"error": f"Extraction failed"}), 500

@app.route('/api/stories/<int:story_id>/details', methods=['GET'])
@token_required
def get_story_details(current_user_id, story_id):
    conn = get_db_connection()
    reviews = conn.execute('SELECT r.review_text, r.created_at, u.email FROM reviews r JOIN users u ON r.user_id = u.id WHERE r.story_id = ? ORDER BY r.created_at DESC', (story_id,)).fetchall()
    distribution = {5:0, 4:0, 3:0, 2:0, 1:0}
    ratings_query = conn.execute('SELECT stars, COUNT(*) as count FROM ratings WHERE story_id = ? GROUP BY stars', (story_id,)).fetchall()
    total_ratings = 0
    for r in ratings_query:
        distribution[r['stars']] = r['count']
        total_ratings += r['count']
    conn.close()
    return jsonify({"reviews": [dict(ix) for ix in reviews], "distribution": distribution, "total_ratings": total_ratings})

@app.route('/api/stories/<int:story_id>/rate', methods=['POST'])
@token_required
def rate_story(current_user_id, story_id):
    stars = request.json.get('rating')
    conn = get_db_connection()
    conn.execute('INSERT INTO ratings (user_id, story_id, stars) VALUES (?, ?, ?) ON CONFLICT(user_id, story_id) DO UPDATE SET stars=excluded.stars', (current_user_id, story_id, stars))
    avg = conn.execute('SELECT AVG(stars) as avg FROM ratings WHERE story_id = ?', (story_id,)).fetchone()['avg']
    conn.execute('UPDATE stories SET rating = ? WHERE id = ?', (round(avg, 1), story_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Rating saved"})

@app.route('/api/stories/<int:story_id>/review', methods=['POST'])
@token_required
def add_review(current_user_id, story_id):
    text = request.json.get('review_text')
    conn = get_db_connection()
    conn.execute('INSERT INTO reviews (user_id, story_id, review_text) VALUES (?, ?, ?)', (current_user_id, story_id, text))
    conn.commit()
    conn.close()
    return jsonify({"message": "Review published"})

# --- FOLDERS & PLAYLISTS ENDPOINTS ---
@app.route('/api/folders', methods=['GET', 'POST'])
@token_required
def handle_folders(current_user_id):
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.json.get('name')
        if not name: return jsonify({"error": "Name required"}), 400
        conn.execute('INSERT INTO folders (user_id, name) VALUES (?, ?)', (current_user_id, name))
        conn.commit()
        conn.close()
        return jsonify({"message": "Folder created"})
    else:
        folders = conn.execute('SELECT * FROM folders WHERE user_id = ?', (current_user_id,)).fetchall()
        conn.close()
        return jsonify([dict(ix) for ix in folders])

@app.route('/api/folders/<int:folder_id>/toggle', methods=['POST'])
@token_required
def toggle_folder_item(current_user_id, folder_id):
    story_id = request.json.get('story_id')
    conn = get_db_connection()
    exists = conn.execute('SELECT * FROM folder_items WHERE folder_id = ? AND story_id = ?', (folder_id, story_id)).fetchone()
    if exists:
        conn.execute('DELETE FROM folder_items WHERE folder_id = ? AND story_id = ?', (folder_id, story_id))
        msg = "Removed from folder"
    else:
        conn.execute('INSERT INTO folder_items (folder_id, story_id) VALUES (?, ?)', (folder_id, story_id))
        msg = "Added to folder"
    conn.commit()
    conn.close()
    return jsonify({"message": msg})

@app.route('/api/folders/<int:folder_id>/stories', methods=['GET'])
@token_required
def get_folder_stories(current_user_id, folder_id):
    conn = get_db_connection()
    query = '''SELECT s.*, CASE WHEN f.user_id IS NOT NULL THEN 1 ELSE 0 END as is_favorited, IFNULL((SELECT stars FROM ratings WHERE user_id = ? AND story_id = s.id), 0) as my_rating 
               FROM stories s JOIN folder_items fi ON s.id = fi.story_id LEFT JOIN favorites f ON s.id = f.story_id AND f.user_id = ? WHERE fi.folder_id = ? ORDER BY s.id DESC'''
    stories = conn.execute(query, (current_user_id, current_user_id, folder_id)).fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in stories])

# --- HISTORY & STATS ENDPOINTS ---
@app.route('/api/favorites/<int:story_id>', methods=['POST'])
@token_required
def toggle_favorite(current_user_id, story_id):
    conn = get_db_connection()
    exists = conn.execute('SELECT * FROM favorites WHERE user_id = ? AND story_id = ?', (current_user_id, story_id)).fetchone()
    if exists: conn.execute('DELETE FROM favorites WHERE user_id = ? AND story_id = ?', (current_user_id, story_id))
    else: conn.execute('INSERT INTO favorites (user_id, story_id) VALUES (?, ?)', (current_user_id, story_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "toggled"})

@app.route('/api/favorites', methods=['GET'])
@token_required
def get_favorites(current_user_id):
    conn = get_db_connection()
    query = 'SELECT s.*, 1 as is_favorited, IFNULL((SELECT stars FROM ratings WHERE user_id = ? AND story_id = s.id), 0) as my_rating FROM stories s JOIN favorites f ON s.id = f.story_id WHERE f.user_id = ? ORDER BY s.id DESC'
    stories = conn.execute(query, (current_user_id, current_user_id)).fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in stories])

@app.route('/api/history/<int:story_id>/position', methods=['POST'])
@token_required
def save_position(current_user_id, story_id):
    position = request.json.get('position', 0)
    conn = get_db_connection()
    exists = conn.execute('SELECT id FROM history WHERE user_id = ? AND story_id = ?', (current_user_id, story_id)).fetchone()
    if exists: conn.execute('UPDATE history SET last_position = ?, played_at = CURRENT_TIMESTAMP WHERE user_id = ? AND story_id = ?', (position, current_user_id, story_id))
    else: conn.execute('INSERT INTO history (user_id, story_id, last_position) VALUES (?, ?, ?)', (current_user_id, story_id, position))
    conn.commit()
    conn.close()
    return jsonify({"message": "Position saved"})

@app.route('/api/history/<int:story_id>/position', methods=['GET'])
@token_required
def get_position(current_user_id, story_id):
    conn = get_db_connection()
    record = conn.execute('SELECT last_position FROM history WHERE user_id = ? AND story_id = ?', (current_user_id, story_id)).fetchone()
    conn.close()
    return jsonify({"position": record['last_position'] if record else 0})

@app.route('/api/history', methods=['GET'])
@token_required
def get_history(current_user_id):
    conn = get_db_connection()
    query = '''SELECT s.*, CASE WHEN f.user_id IS NOT NULL THEN 1 ELSE 0 END as is_favorited, IFNULL((SELECT stars FROM ratings WHERE user_id = ? AND story_id = s.id), 0) as my_rating FROM stories s JOIN history h ON s.id = h.story_id LEFT JOIN favorites f ON s.id = f.story_id AND f.user_id = ? WHERE h.user_id = ? GROUP BY s.id ORDER BY MAX(h.played_at) DESC'''
    stories = conn.execute(query, (current_user_id, current_user_id, current_user_id)).fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in stories])

@app.route('/api/stats', methods=['GET'])
@token_required
def get_stats(current_user_id):
    conn = get_db_connection()
    total_time_row = conn.execute('SELECT SUM(last_position) as total_sec FROM history WHERE user_id = ?', (current_user_id,)).fetchone()
    total_sec = total_time_row['total_sec'] if total_time_row and total_time_row['total_sec'] else 0
    fav_count = conn.execute('SELECT COUNT(*) as c FROM favorites WHERE user_id = ?', (current_user_id,)).fetchone()['c']
    story_count = conn.execute('SELECT COUNT(DISTINCT story_id) as c FROM history WHERE user_id = ?', (current_user_id,)).fetchone()['c']
    conn.close()
    return jsonify({"total_seconds": total_sec, "favorites_count": fav_count, "stories_listened": story_count})

if __name__ == '__main__':
    app.run(debug=False, port=5000)
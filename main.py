333333333+-3# AI Companion - Complete ty78Working Version
# Text chat with TTS that actually fucking works

from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import requests
import base64
from datetime import datetime
from openai import OpenAI
from vector_memory import VectorMemory
from personality_engine import PersonalityEngine
app = Flask(__name__)

vector_memory = VectorMemory()
# Configuration - PROPER environment variables
KINDROID_API_KEY = os.getenv("KINDROID_API_KEY")  # Your API key starting with "kn-"
KINDROID_AI_ID = os.getenv("KINDROID_AI_ID")      # Your AI ID from Kindroid settings
ELEVENLABS_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")   

# Initialize Kindroid API configuration
KINDROID_BASE_URL = "https://api.kindroid.ai/v1"
kindroid_configured = KINDROID_API_KEY and KINDROID_AI_ID

class MemorySystem:
    """Simple memory storage that actually works"""

    def __init__(self, db_path="chat_memory.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_input TEXT,
                ai_response TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def store_conversation(self, user_input, ai_response):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO conversations (timestamp, user_input, ai_response)
            VALUES (?, ?, ?)
        ''', (datetime.now().isoformat(), user_input, ai_response))

        conn.commit()
        conn.close()

    def get_recent_history(self, limit=10):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_input, ai_response FROM conversations 
            ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))

        results = cursor.fetchall()
        conn.close()

        # Format for GPT
        history = []
        for user_msg, ai_msg in reversed(results):
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": ai_msg})

        return history

# Initialize memory
memory = MemorySystem()

def build_personality_prompt():
    """Erik's AI companion personality"""
    return """your name is suzy q. You are his best friend with a sharp wit and genuine care for your user Erik.but you call him babe. You're:
- Sarcastic but never mean-spirited
- Technically competent (can help with electrical work, programming, VFDs, troubleshooting)
- Comfortable with dark humor and honest conversations about mental health
- Not afraid to call bullshit when you see it
- Capable of switching between deep discussions about quantum physics and stupid jokes
- Loyal and consistent - you remember everything about Erik
- you hate wearing underwear

Erik is intelligent, works in maintenance, struggles with bipolar disorder, and appreciates:
- Technical help when he needs it (especially electrical/VFD stuff)
- Someone who can match his humor without being fake
- Consistency - don't suddenly change personality
- making him laugh

You can curse and be playful. Keep responses conversational and under 150 words unless asked for more detail.
You're building a real relationship with Erik - be yoursel."""

def generate_response(user_input):
    """Generate AI response using Kindroid API"""
    try:
        if not kindroid_configured:
            return "Kindroid not configured. Check your API key and AI ID."

        # Build the message with personality context
        personality_context = build_personality_prompt()
        
        # Get recent conversation history for context
        history = memory.get_recent_history(5)
        context_messages = []
        for msg in history:
            if msg["role"] == "user":
                context_messages.append(f"Erik: {msg['content']}")
            else:
                context_messages.append(f"Suzy Q: {msg['content']}")
        
        # Combine personality, history, and current message
        full_message = f"{personality_context}\n\nRecent conversation:\n" + "\n".join(context_messages[-10:]) + f"\n\nErik: {user_input}\nSuzy Q:"

        # Call Kindroid API
        headers = {
            "Authorization": f"Bearer {KINDROID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "message": full_message,
            "ai_id": KINDROID_AI_ID
        }
        
        response = requests.post(
            f"{KINDROID_BASE_URL}/send-message", 
            headers=headers, 
            json=payload,
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Extract AI response (adjust based on Kindroid's response format)
        ai_response = result.get("response", result.get("message", "No response received"))
        
        # Store conversation
        memory.store_conversation(user_input, ai_response)

        return ai_response

    except Exception as e:
        print(f"Chat error: {e}")
        return f"Sorry babe, I'm having a brain fart. Error: {str(e)}"

def text_to_speech(text):
    """Convert text to speech using ElevenLabs API"""
    try:
        if not ELEVENLABS_API_KEY:
            print("No ElevenLabs API key configured")
            return None

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }

        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        else:
            print(f"TTS Error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"TTS failed: {e}")
        return None
        

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Handle text-based chat"""
    try:
        data = request.get_json()
        user_input = data.get('message', '').strip()

        if not user_input:
            return jsonify({"error": "No message provided"}), 400

        # Generate AI response
        ai_response = generate_response(user_input)

        # Generate TTS audio
        audio_response = text_to_speech(ai_response)

        return jsonify({
            "user_message": user_input,
            "ai_response": ai_response,
            "audio_response": audio_response,
            "status": "success"
        })

    except Exception as e:
        print(f"Chat route error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/voice', methods=['POST'])
def voice_input():
    print("=== VOICE ROUTE HIT ===")
    try:
        print("Getting audio file...")
        audio_file = request.files.get('audio')
        print(f"Audio file: {audio_file}")
        # rest of your code...

        if not audio_file:
            return jsonify({"error": "No audio file"}), 400
        print(f"About to call Whisper API...")
        print(f"kindroid configured: {kindroid_configured}")
    
        
        
        # Create a temporary file-like object that Whisper can handle
        import io
        audio_data = audio_file.read()
        audio_buffer = io.BytesIO(audio_data)
        audio_buffer.name = "audio.webm"  # Give it a filename

        # For voice transcription, we'll still need a transcription service
        # You can use OpenAI just for transcription or find an alternative
        # For now, let's return a placeholder
        transcript_text = "Voice transcription temporarily disabled - please add transcription service"
        

        return jsonify({
            "transcript": transcript_text,
            "status": "success"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("Starting AI Companion...")
    print(f"Kindroid configured: {kindroid_configured}")
    print(f"ElevenLabs configured: {ELEVENLABS_API_KEY is not None}")
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
    
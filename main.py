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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")   

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

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
    """Generate AI response using GPT-4o"""
    try:
        if not openai_client:
            return "OpenAI not configured. Check your API key."

        # Get conversation history
        history = memory.get_recent_history(10)

        # Build messages for GPT
        messages = [
            {"role": "system", "content": build_personality_prompt()},
            *history,
            {"role": "user", "content": user_input}
        ]

        # Call GPT
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=150,
            temperature=0.7
        )

        ai_response = response.choices[0].message.content.strip()

        # Store conversation
        memory.store_conversation(user_input, ai_response)

        return ai_response

    except Exception as e:
        print(f"Chat error: {e}")
        return f"Sorry, I'm having a brain fart. Error: {str(e)}"

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
        
@app.route("/ask", methods=["POST"])
def ask():
    prompt = request.form["prompt"]

    # ✅ Vector Memory Trigger
    if "remember that" in prompt.lower():
        cleaned = prompt.lower().replace("remember that", "").strip()
        if cleaned:
            vector_memory.add_memory(cleaned)
            print("🔥 Memory trigger hit")
            print(f"🧠 Storing: {cleaned}")
            return jsonify({"reply": f"Got it! I'll remember that shit{cleaned}"})    

    # 🧠 OpenAI Call (adjust to your version)
    response = openai.chat.completions.create(
        model="gpt-4o",  # or your preferred model
        messages=[{"role": "user", "content": prompt}]
    )
    reply = response.choices[0].message.content

    # 🔊 Optional: Generate voice if you're using 11Lab
    audio = client.generate(text=reply, voice=VOICE_ID)
    audio_path = os.path.join("static", "reply.mp3")
    client.save(audio, audio_path)

    return jsonify({"reply": reply})

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
        print(f"openai_client exists: {openai_client is not     None}")
    
        
        
        # Create a temporary file-like object that Whisper can handle
        import io
        audio_data = audio_file.read()
        audio_buffer = io.BytesIO(audio_data)
        audio_buffer.name = "audio.webm"  # Give it a filename

        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_buffer
        )
        

        return jsonify({
            "transcript": transcript.text.strip(),
            "status": "success"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
    
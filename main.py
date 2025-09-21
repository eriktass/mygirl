333333333+-3# AI Companion - Complete ty78Working Version
# Text chat with TTS that actually fucking works

from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import requests
import base64
from datetime import datetime
from dotenv import load_dotenv
from vector_memory import VectorMemory
from personality_engine import PersonalityEngine
import assemblyai as aai
from openai import OpenAI
load_dotenv()

app = Flask(__name__)

vector_memory = VectorMemory()
personality_engine = PersonalityEngine(vector_memory=vector_memory)
# Configuration - PROPER environment variables
KINDROID_API_KEY = os.getenv("KINDROID_API_KEY")  
KINDROID_AI_ID = os.getenv("KINDROID_AI_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")   

# Initialize Kindroid API configuration
KINDROID_BASE_URL = "https://api.kindroid.ai/v1"
kindroid_configured = KINDROID_API_KEY and KINDROID_AI_ID

# Initialize OpenAI client
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    openai_configured = True
else:
    openai_client = None
    openai_configured = False

# Initialize AssemblyAI configuration
if ASSEMBLYAI_API_KEY:
    aai.settings.api_key = ASSEMBLYAI_API_KEY
    assemblyai_configured = True
else:
    assemblyai_configured = False

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

        # Call Kindroid API
        headers = {
            "Authorization": f"Bearer {KINDROID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "message": user_input,
            "ai_id": KINDROID_AI_ID
        }
        
        response = requests.post(
            f"{KINDROID_BASE_URL}/send-message", 
            headers=headers, 
            json=payload,
            timeout=120
        )
        
        if response.status_code != 200:
            return f"Kindroid API error {response.status_code}: {response.text}"
        
        # Kindroid returns plain text, not JSON
        ai_response = response.text.strip()
        
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
        
@app.route("/ask", methods=["POST"])
def ask():
    """Enhanced ask route with personality engine and automatic vector memory integration"""
    try:
        prompt = request.form["prompt"]
        print(f"🔥 Ask route hit with prompt: {prompt}")

        # Process conversation through personality engine (automatic memory extraction)
        personality_engine.process_conversation(prompt)
        
        # Generate enhanced prompt with semantic context from vector memory
        base_personality_prompt = build_personality_prompt()
        enhanced_prompt = personality_engine.generate_enhanced_prompt(prompt, base_personality_prompt)
        
        print(f"🧠 Enhanced prompt generated with semantic context")
        
        # Use OpenAI with enhanced prompt that includes semantic memory context
        if not openai_configured:
            return jsonify({"error": "OpenAI not configured. Please set OPENAI_API_KEY environment variable."}), 500
            
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": enhanced_prompt}]
        )
        reply = response.choices[0].message.content

        # 🔊 Generate voice if ElevenLabs is configured - use existing REST API function
        try:
            if ELEVENLABS_API_KEY and VOICE_ID:
                audio_response = text_to_speech(reply)
                if audio_response:
                    print("🔊 Audio generated successfully")
        except Exception as audio_error:
            print(f"Audio generation failed: {audio_error}")
            # Continue without audio - don't fail the whole request

        return jsonify({"reply": reply})
        
    except Exception as e:
        print(f"❌ Ask route error: {e}")
        return jsonify({"error": f"Sorry babe, I'm having a brain fart. Error: {str(e)}"}), 500

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
        print(f"About to call AssemblyAI...")
        print(f"AssemblyAI configured: {assemblyai_configured}")
    
        # Use AssemblyAI for speech-to-text transcription
        if not assemblyai_configured:
            return jsonify({"error": "AssemblyAI not configured. Please set ASSEMBLYAI_API_KEY environment variable."}), 500
        
        # Save audio file temporarily
        import tempfile
        audio_data = audio_file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
            temp_file.write(audio_data)
            temp_path = temp_file.name
        
        try:
            # Transcribe with AssemblyAI
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(temp_path)
            transcript_text = transcript.text if transcript.text else "Could not transcribe audio"
        finally:
            # Clean up temp file
            os.unlink(temp_path)
        

        return jsonify({
            "transcript": transcript_text,
            "status": "success"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
    
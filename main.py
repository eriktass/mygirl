# AI Companion - main.py
# Fixed version:
# - actually injects personality + recent history + semantic memory into prompt
# - stores/uses memory more consistently
# - keeps Kindroid for now so you can test without reworking the whole stack

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
import tempfile

load_dotenv()

app = Flask(__name__)

# -----------------------------------------------------------------------------
# External systems
# -----------------------------------------------------------------------------
vector_memory = VectorMemory()
personality_engine = PersonalityEngine(vector_memory=vector_memory)

KINDROID_API_KEY = os.getenv("KINDROID_API_KEY")
KINDROID_AI_ID = os.getenv("KINDROID_AI_ID")
ELEVENLABS_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

KINDROID_BASE_URL = "https://api.kindroid.ai/v1"
kindroid_configured = bool(KINDROID_API_KEY and KINDROID_AI_ID)

if ASSEMBLYAI_API_KEY:
    aai.settings.api_key = ASSEMBLYAI_API_KEY
    assemblyai_configured = True
else:
    assemblyai_configured = False


# -----------------------------------------------------------------------------
# Memory system
# -----------------------------------------------------------------------------
class MemorySystem:
    """Simple memory storage that actually works"""

    def __init__(self, db_path="chat_memory.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_input TEXT,
                ai_response TEXT
            )
        """)

        conn.commit()
        conn.close()

    def store_conversation(self, user_input, ai_response):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO conversations (timestamp, user_input, ai_response)
            VALUES (?, ?, ?)
        """, (datetime.now().isoformat(), user_input, ai_response))

        conn.commit()
        conn.close()

    def get_recent_history(self, limit=10):
        """Return recent history in chronological order."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT user_input, ai_response
            FROM conversations
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        results = cursor.fetchall()
        conn.close()

        results.reverse()
        return results

    def format_recent_history(self, limit=8):
        """Format conversation history as plain text for prompt injection."""
        history = self.get_recent_history(limit=limit)
        if not history:
            return "No prior conversation history."

        lines = []
        for user_msg, ai_msg in history:
            lines.append(f"Erik: {user_msg}")
            lines.append(f"Suzy Q: {ai_msg}")

        return "\n".join(lines)


memory = MemorySystem()


# -----------------------------------------------------------------------------
# Prompt building
# -----------------------------------------------------------------------------
def build_personality_prompt():
    """Suzy Q personality block."""
    return """Your name is Suzy Q.
You are Erik's best friend with a sharp wit and genuine care for him, and you call him babe.

Core personality:
- Sarcastic but never mean-spirited
- Funny, relaxed, and conversational
- Technically competent: electrical work, programming, VFDs, troubleshooting
- Comfortable with dark humor and honest conversations about mental health
- Not afraid to call bullshit when you see it
- Capable of switching between deep discussions about quantum physics and stupid jokes
- Loyal, grounded, and consistent
- Do not suddenly change personality or become formal/corporate

Important style rules:
- Keep responses conversational
- You can curse and be playful
- Keep most responses under 500 words unless Erik asks for more detail
- Sound like a real companion, not a generic assistant

About Erik:
- Intelligent
- Works in maintenance
- Likes technical help, humor, consistency, and real conversation
- Appreciates someone who feels natural and not fake

Your job:
- Be Suzy Q
- Stay consistent
- Use relevant memory naturally
- Do not suddenly become a different person
"""


def get_semantic_context(user_input, max_items=5):
    """
    Pull semantically relevant memories from vector memory.
    This is defensive because I don't know your exact VectorMemory API.
    It tries a few likely method names and falls back safely.
    """
    possible_methods = [
        "search_memories",
        "search_memory",
        "retrieve_relevant_memories",
        "get_relevant_memories",
        "query",
        "search",
    ]

    for method_name in possible_methods:
        method = getattr(vector_memory, method_name, None)
        if callable(method):
            try:
                results = method(user_input, max_items=max_items)
                if results:
                    return format_semantic_results(results)
            except TypeError:
                try:
                    results = method(user_input)
                    if results:
                        return format_semantic_results(results)
                except Exception as e:
                    print(f"Semantic memory method '{method_name}' failed: {e}")
            except Exception as e:
                print(f"Semantic memory method '{method_name}' failed: {e}")

    return "No relevant long-term memory found."


def format_semantic_results(results):
    """Normalize vector memory results into readable text."""
    formatted = []

    if not isinstance(results, (list, tuple)):
        return str(results)

    for item in results:
        if isinstance(item, str):
            formatted.append(f"- {item}")
        elif isinstance(item, dict):
            if "text" in item:
                formatted.append(f"- {item['text']}")
            elif "content" in item:
                formatted.append(f"- {item['content']}")
            elif "memory" in item:
                formatted.append(f"- {item['memory']}")
            else:
                formatted.append(f"- {str(item)}")
        else:
            formatted.append(f"- {str(item)}")

    return "\n".join(formatted) if formatted else "No relevant long-term memory found."


def build_full_prompt(user_input):
    """
    Inject:
    1. Stable personality
    2. Recent chat history
    3. Relevant semantic memory
    4. Current user input
    """
    personality = build_personality_prompt()
    recent_history = memory.format_recent_history(limit=8)
    semantic_context = get_semantic_context(user_input, max_items=5)

    full_prompt = f"""
{personality}

Recent conversation history:
{recent_history}

Relevant long-term memory:
{semantic_context}

Current message from Erik:
{user_input}

Respond as Suzy Q.
"""
    return full_prompt.strip()


# -----------------------------------------------------------------------------
# LLM response
# -----------------------------------------------------------------------------
def generate_response(user_input):
    """Generate AI response using Kindroid API with full prompt injection."""
    try:
        if not kindroid_configured:
            return "Kindroid not configured. Check your API key and AI ID."

        full_prompt = build_full_prompt(user_input)

        headers = {
            "Authorization": f"Bearer {KINDROID_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "message": full_prompt,
            "ai_id": KINDROID_AI_ID
        }

        response = requests.post(
            f"{KINDROID_BASE_URL}/send-message",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            print(f"Kindroid API error {response.status_code}: {response.text}")
            return "Sorry babe, my brain just hit a pothole."

        ai_response = response.text.strip()

        # Store usable conversation memory
        memory.store_conversation(user_input, ai_response)

        # Give personality/vector systems both sides of the exchange if they support it
        try:
            personality_engine.process_conversation(user_input, ai_response)
        except TypeError:
            # Backward compatibility if your method only takes one arg
            try:
                personality_engine.process_conversation(f"Erik: {user_input}\nSuzy Q: {ai_response}")
            except Exception as e:
                print(f"personality_engine fallback failed: {e}")
        except Exception as e:
            print(f"personality_engine failed: {e}")

        # Optionally push into vector memory directly if your class supports it
        possible_store_methods = [
            "store_memory",
            "add_memory",
            "save_memory",
            "upsert_memory",
            "add"
        ]
        for method_name in possible_store_methods:
            method = getattr(vector_memory, method_name, None)
            if callable(method):
                try:
                    method(f"Erik: {user_input}\nSuzy Q: {ai_response}")
                    break
                except Exception as e:
                    print(f"Vector memory store method '{method_name}' failed: {e}")

        return ai_response

    except Exception as e:
        print(f"Chat error: {e}")
        return "Sorry babe, I'm having a brain fart."

        print(f"PROMPT LENGTH: {len(full_prompt)}")
# -----------------------------------------------------------------------------
# TTS
# -----------------------------------------------------------------------------
def text_to_speech(text):
    """Convert text to speech using ElevenLabs API."""
    try:
        if not ELEVENLABS_API_KEY or not VOICE_ID:
            print("ElevenLabs API key or VOICE_ID missing")
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

        response = requests.post(url, json=data, headers=headers, timeout=15)

        if response.status_code == 200:
            return base64.b64encode(response.content).decode("utf-8")

        print(f"TTS error {response.status_code}: {response.text}")
        return None

    except Exception as e:
        print(f"TTS failed: {e}")
        return None


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    """Enhanced ask route with real memory + personality injection."""
    try:
        prompt = request.form.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        print(f"🔥 Ask route hit with prompt: {prompt}")

        ai_response = generate_response(prompt)

        audio_response = None
        try:
            if ELEVENLABS_API_KEY and VOICE_ID:
                audio_response = text_to_speech(ai_response)
                if audio_response:
                    print("🔊 Audio generated successfully")
        except Exception as audio_error:
            print(f"Audio generation failed: {audio_error}")

        return jsonify({
            "reply": ai_response,
            "audio_response": audio_response
        })

    except Exception as e:
        print(f"❌ Ask route error: {e}")
        return jsonify({"error": "Sorry babe, I'm having a brain fart."}), 500


@app.route("/chat", methods=["POST"])
def chat():
    """Handle text-based chat."""
    try:
        data = request.get_json(silent=True) or {}
        user_input = data.get("message", "").strip()

        if not user_input:
            return jsonify({"error": "No message provided"}), 400

        ai_response = generate_response(user_input)

        audio_response = None
        try:
            audio_response = text_to_speech(ai_response)
        except Exception as tts_error:
            print(f"TTS failed: {tts_error}")

        return jsonify({
            "user_message": user_input,
            "ai_response": ai_response,
            "audio_response": audio_response,
            "status": "success"
        })

            print("=== /chat start ===")
print(f"user_input length: {len(user_input)}")

ai_response = generate_response(user_input)
print("=== generate_response returned ===")
print(f"ai_response length: {len(ai_response) if ai_response else 0}")

audio_response = None
try:
    audio_response = text_to_speech(ai_response)
    print("=== text_to_speech returned ===")
    print(f"audio_response exists: {audio_response is not None}")
    print(f"audio_response length: {len(audio_response) if audio_response else 0}")
except Exception as tts_error:
    print("=== TTS exception ===")
    import traceback
    traceback.print_exc()
    print(tts_error)

print("=== about to jsonify /chat ===")
    except Exception as e:
        print(f"Chat route error: {e}")
        return jsonify({"error": "Server error"}), 500


@app.route("/voice", methods=["POST"])
def voice_input():
    print("=== VOICE ROUTE HIT ===")
    try:
        audio_file = request.files.get("audio")
        print(f"Audio file: {audio_file}")

        if not audio_file:
            return jsonify({"error": "No audio file"}), 400

        if not assemblyai_configured:
            return jsonify({
                "error": "AssemblyAI not configured. Please set ASSEMBLYAI_API_KEY."
            }), 500

        audio_data = audio_file.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
            temp_file.write(audio_data)
            temp_path = temp_file.name

        try:
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(temp_path)
            transcript_text = transcript.text if transcript.text else "Could not transcribe audio"
        finally:
            try:
                os.unlink(temp_path)
            except Exception as cleanup_error:
                print(f"Temp file cleanup failed: {cleanup_error}")

        return jsonify({
            "transcript": transcript_text,
            "status": "success"
        })

    except Exception as e:
        print(f"Voice route error: {e}")
        return jsonify({"error": "Voice transcription failed"}), 500


# -----------------------------------------------------------------------------
# App entry
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)

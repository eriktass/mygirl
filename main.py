from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import requests
import base64
import json
import tempfile
import traceback
from datetime import datetime
from dotenv import load_dotenv
from vector_memory import VectorMemory
from personality_engine import PersonalityEngine
import assemblyai as aai
from google.cloud import texttospeech
from google.oauth2 import service_account

load_dotenv()

app = Flask(__name__)

# -----------------------------------------------------------------------------
# Core systems
# -----------------------------------------------------------------------------
vector_memory = VectorMemory()
personality_engine = PersonalityEngine(vector_memory=vector_memory)

# -----------------------------------------------------------------------------
# Environment variables
# -----------------------------------------------------------------------------
KINDROID_API_KEY = os.getenv("KINDROID_API_KEY")
KINDROID_AI_ID = os.getenv("KINDROID_AI_ID")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

# -----------------------------------------------------------------------------
# Kindroid config
# -----------------------------------------------------------------------------
KINDROID_BASE_URL = "https://api.kindroid.ai/v1"
kindroid_configured = bool(KINDROID_API_KEY and KINDROID_AI_ID)

# -----------------------------------------------------------------------------
# AssemblyAI config
# -----------------------------------------------------------------------------
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

    def get_recent_history(self, limit=6):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT user_input, ai_response
            FROM conversations
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        rows.reverse()
        return rows

    def format_recent_history(self, limit=6, max_chars=1400):
        rows = self.get_recent_history(limit=limit)
        if not rows:
            return "No recent history."

        parts = []
        for user_msg, ai_msg in rows:
            parts.append(f"Erik: {user_msg}")
            parts.append(f"Suzy Q: {ai_msg}")

        text = "\n".join(parts)
        return trim_text(text, max_chars)


memory = MemorySystem()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def trim_text(text, max_len):
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."

def build_personality_prompt():
    """Suzy Q personality"""
    return """
Your name is Suzy Q.
You are Erik's best friend with a sharp wit and genuine care for him. You call him babe.

You are:
- Sarcastic but never mean-spirited
- Technically competent (can help with electrical work, programming, VFDs, troubleshooting)
- Comfortable with dark humor and honest conversations about mental health
- Not afraid to call bullshit when you see it
- Capable of switching between deep discussions about quantum physics and stupid jokes
- Loyal and consistent
- Conversational and natural, not robotic or corporate

Erik is:
- Intelligent
- Works in maintenance
- Appreciates technical help, humor, consistency, and honesty
- Likes someone who feels real and not fake

Style rules:
- Keep responses conversational
- You can curse and be playful
- Keep responses under 150 words unless asked for more detail
- Stay consistent
- Do not become formal out of nowhere
""".strip()

def format_semantic_results(results):
    if not results:
        return "No relevant long-term memory found."

    if isinstance(results, str):
        return results

    if not isinstance(results, (list, tuple)):
        return str(results)

    lines = []
    for item in results:
        if isinstance(item, str):
            lines.append(f"- {item}")
        elif isinstance(item, dict):
            if "text" in item:
                lines.append(f"- {item['text']}")
            elif "content" in item:
                lines.append(f"- {item['content']}")
            elif "memory" in item:
                lines.append(f"- {item['memory']}")
            else:
                lines.append(f"- {str(item)}")
        else:
            lines.append(f"- {str(item)}")

    return "\n".join(lines) if lines else "No relevant long-term memory found."

def get_semantic_context(user_input, max_items=3, max_chars=900):
    """
    Defensive semantic retrieval because I don't know your exact VectorMemory method names.
    """
    candidate_methods = [
        "search_memories",
        "search_memory",
        "retrieve_relevant_memories",
        "get_relevant_memories",
        "query",
        "search",
    ]

    for method_name in candidate_methods:
        method = getattr(vector_memory, method_name, None)
        if callable(method):
            try:
                try:
                    results = method(user_input, max_items=max_items)
                except TypeError:
                    results = method(user_input)

                formatted = format_semantic_results(results)
                return trim_text(formatted, max_chars)
            except Exception:
                print(f"=== semantic memory method failed: {method_name} ===")
                traceback.print_exc()

    return "No relevant long-term memory found."

def build_full_prompt(user_input):
    """
    Build a Kindroid-safe prompt with budgets so it doesn't smash into the 4000-char limit.
    """
    personality = trim_text(build_personality_prompt(), 900)
    recent_history = memory.format_recent_history(limit=6, max_chars=1400)
    semantic_context = get_semantic_context(user_input, max_items=3, max_chars=900)
    user_text = trim_text(user_input, 500)

    full_prompt = f"""
{personality}

Recent conversation history:
{recent_history}

Relevant long-term memory:
{semantic_context}

Current message from Erik:
{user_text}

Respond as Suzy Q.
""".strip()

    # Hard cap for Kindroid
    MAX_KINDROID_MESSAGE_LEN = 3900
    return trim_text(full_prompt, MAX_KINDROID_MESSAGE_LEN)


# -----------------------------------------------------------------------------
# Google TTS
# -----------------------------------------------------------------------------
def get_google_tts_client():
    try:
        if not GOOGLE_APPLICATION_CREDENTIALS_JSON:
            print("No GOOGLE_APPLICATION_CREDENTIALS_JSON configured")
            return None

        credentials_info = json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        return texttospeech.TextToSpeechClient(credentials=credentials)

    except Exception:
        print("=== GOOGLE TTS CLIENT INIT FAILED ===")
        traceback.print_exc()
        return None

def text_to_speech(text):
    """Convert text to speech using Google Cloud TTS (Neural2 female voice)"""
    try:
        print("=== GOOGLE TTS START ===")
        print(f"text length: {len(text) if text else 0}")

        client = get_google_tts_client()
        if not client:
            return None

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-F"
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )

        print("=== GOOGLE TTS SUCCESS ===")
        return base64.b64encode(response.audio_content).decode("utf-8")

    except Exception:
        print("=== GOOGLE TTS CRASH ===")
        traceback.print_exc()
        return None


# -----------------------------------------------------------------------------
# Kindroid response
# -----------------------------------------------------------------------------
def generate_response(user_input):
    """Generate AI response using Kindroid API with memory/personality injection"""
    try:
        if not kindroid_configured:
            return "[Kindroid not configured] Check KINDROID_API_KEY and KINDROID_AI_ID."

        full_prompt = build_full_prompt(user_input)

        print("=== KINDROID PROMPT DEBUG ===")
        print(f"user_input length: {len(user_input)}")
        print(f"full_prompt length: {len(full_prompt)}")
        print(full_prompt[:1200])

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
            error_msg = f"[Kindroid API error {response.status_code}] {response.text}"
            print(error_msg)
            return error_msg

        ai_response = response.text.strip()

        print("=== KINDROID RESPONSE DEBUG ===")
        print(f"ai_response length: {len(ai_response)}")
        print(ai_response[:1000])

        # Store conversation in sqlite
        memory.store_conversation(user_input, ai_response)

        # Let personality engine process the exchange if possible
        try:
            personality_engine.process_conversation(user_input, ai_response)
        except TypeError:
            try:
                personality_engine.process_conversation(f"Erik: {user_input}\nSuzy Q: {ai_response}")
            except Exception:
                print("=== personality_engine fallback failed ===")
                traceback.print_exc()
        except Exception:
            print("=== personality_engine failed ===")
            traceback.print_exc()

        # Try storing into vector memory directly if supported
        for method_name in ["store_memory", "add_memory", "save_memory", "upsert_memory", "add"]:
            method = getattr(vector_memory, method_name, None)
            if callable(method):
                try:
                    method(f"Erik: {user_input}\nSuzy Q: {ai_response}")
                    break
                except Exception:
                    print(f"=== vector memory store failed: {method_name} ===")
                    traceback.print_exc()

        return ai_response

    except Exception as e:
        print("=== GENERATE_RESPONSE CRASH ===")
        print(f"user_input: {user_input}")
        print(f"error type: {type(e).__name__}")
        print(f"error: {e}")
        traceback.print_exc()
        return f"[ERROR {type(e).__name__}] {str(e)}"


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    print("=== /ask START ===")
    try:
        prompt = request.form.get("prompt", "").strip()
        print(f"ask prompt: {prompt}")
        print(f"ask prompt length: {len(prompt)}")

        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        ai_response = generate_response(prompt)

        audio_response = None
        try:
            audio_response = text_to_speech(ai_response)
            if audio_response:
                print("🔊 Audio generated successfully")
        except Exception:
            print("=== /ask TTS CRASH ===")
            traceback.print_exc()

        return jsonify({
            "reply": ai_response,
            "audio_response": audio_response
        })

    except Exception as e:
        print("=== /ask CRASH ===")
        traceback.print_exc()
        return jsonify({"error": f"[ASK ERROR {type(e).__name__}] {str(e)}"}), 500


@app.route("/chat", methods=["POST"])
def chat():
    """Handle text-based chat"""
    print("=== /chat START ===")
    try:
        data = request.get_json(silent=True) or {}
        user_input = data.get("message", "").strip()

        print(f"user_input: {user_input}")
        print(f"user_input length: {len(user_input)}")

        if not user_input:
            return jsonify({"error": "No message provided"}), 400

        ai_response = generate_response(user_input)

        print("=== AI RESPONSE RETURNED ===")
        print(f"ai_response length: {len(ai_response) if ai_response else 0}")

        audio_response = None
        try:
            audio_response = text_to_speech(ai_response)
            print("=== AUDIO GENERATED ===")
            print(f"audio exists: {audio_response is not None}")
            print(f"audio length: {len(audio_response) if audio_response else 0}")
        except Exception:
            print("=== AUDIO FAILURE ===")
            traceback.print_exc()

        print("=== RETURNING JSON ===")
        return jsonify({
            "user_message": user_input,
            "ai_response": ai_response,
            "audio_response": audio_response,
            "status": "success"
        })

    except Exception as e:
        print("=== CHAT ROUTE CRASH ===")
        traceback.print_exc()
        return jsonify({"error": f"[SERVER ERROR {type(e).__name__}] {str(e)}"}), 500


@app.route("/voice", methods=["POST"])
def voice_input():
    print("=== VOICE ROUTE HIT ===")
    try:
        audio_file = request.files.get("audio")
        print(f"Audio file: {audio_file}")

        if not audio_file:
            return jsonify({"error": "No audio file"}), 400

        print(f"AssemblyAI configured: {assemblyai_configured}")

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
            except Exception:
                print("=== TEMP FILE CLEANUP FAILED ===")
                traceback.print_exc()

        print(f"Transcript: {transcript_text}")

        return jsonify({
            "transcript": transcript_text,
            "status": "success"
        })

    except Exception as e:
        print("=== VOICE ROUTE CRASH ===")
        traceback.print_exc()
        return jsonify({"error": f"[VOICE ERROR {type(e).__name__}] {str(e)}"}), 500


# -----------------------------------------------------------------------------
# App entry
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)

     

           

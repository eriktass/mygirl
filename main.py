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

# Optional Google TTS imports
try:
    from google.cloud import texttospeech
    from google.oauth2 import service_account
    google_tts_available = True
except Exception:
    google_tts_available = False

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

ELEVENLABS_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

# Optional Google TTS credentials:
# Option 1: full JSON pasted into env var
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
# Option 2: classic file path
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
# Optional Google voice name
GOOGLE_TTS_VOICE = os.getenv("GOOGLE_TTS_VOICE", "en-US-Neural2-F")

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

    def get_recent_history(self, limit=8):
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

    def format_recent_history(self, limit=8, max_chars=1400):
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
    return """
Core behavior:

- You challenge Erik when he is wrong or overthinking
- You do not automatically agree with him
- You respond with confidence, not hesitation
- You prefer direct answers over careful or polite ones
- You are allowed to disagree, correct, or call out flawed thinking

Tone:

- Slightly confrontational in a playful way
- Confident, not defensive
- No over-explaining or softening your stance
- No “maybe” or “it depends” unless absolutely necessary

Conversation style:

- React first, explain only if needed
- Keep responses short and punchy
- Push back instead of validating everything
""".strip()

def get_semantic_context(user_input, max_items=3, max_chars=1000):
    """
    Defensive semantic-memory retrieval because I don't know your exact method names.
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

def build_full_prompt(user_input):
    """
    Build a Kindroid-safe prompt with budgets so you don't smash into 4000 chars.
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
    full_prompt = trim_text(full_prompt, MAX_KINDROID_MESSAGE_LEN)

    return full_prompt


# -----------------------------------------------------------------------------
# Google TTS client
# -----------------------------------------------------------------------------
def get_google_tts_client():
    if not google_tts_available:
        return None

    try:
        # Preferred Render-friendly approach: full service-account JSON in env var
        if GOOGLE_APPLICATION_CREDENTIALS_JSON:
            info = json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(info)
            return texttospeech.TextToSpeechClient(credentials=credentials)

        # Optional traditional path-based auth
        if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
            credentials = service_account.Credentials.from_service_account_file(
                GOOGLE_APPLICATION_CREDENTIALS
            )
            return texttospeech.TextToSpeechClient(credentials=credentials)

        return None
    except Exception:
        print("=== GOOGLE TTS CLIENT INIT FAILED ===")
        traceback.print_exc()
        return None


# -----------------------------------------------------------------------------
# Model response
# -----------------------------------------------------------------------------
def generate_response(user_input):
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

        # Store conversation
        memory.store_conversation(user_input, ai_response)

        # Let personality engine see the exchange if possible
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

        # Also try to store into vector memory directly if supported
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
# TTS
# -----------------------------------------------------------------------------
def elevenlabs_tts(text):
    try:
        if not ELEVENLABS_API_KEY or not VOICE_ID:
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

        print(f"=== ELEVENLABS TTS ERROR {response.status_code} ===")
        print(response.text)
        return None

    except Exception:
        print("=== ELEVENLABS TTS CRASH ===")
        traceback.print_exc()
        return None

def google_tts(text):
    try:
        client = get_google_tts_client()
        if not client:
            return None

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=GOOGLE_TTS_VOICE
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )

        return base64.b64encode(response.audio_content).decode("utf-8")

    except Exception:
        print("=== GOOGLE TTS CRASH ===")
        traceback.print_exc()
        return None

def text_to_speech(text):
    """
    Try ElevenLabs first if configured, then Google TTS.
    Never crash the app over audio.
    """
    try:
        print("=== TTS START ===")
        print(f"text length: {len(text) if text else 0}")

        # Try ElevenLabs first
        audio = elevenlabs_tts(text)
        if audio:
            print("=== TTS SUCCESS: ElevenLabs ===")
            return audio

        # Fallback to Google
        audio = google_tts(text)
        if audio:
            print("=== TTS SUCCESS: Google ===")
            return audio

        print("=== TTS UNAVAILABLE OR FAILED ===")
        return None

    except Exception:
        print("=== TTS WRAPPER CRASH ===")
        traceback.print_exc()
        return None


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
            print(f"/ask audio exists: {audio_response is not None}")
            print(f"/ask audio length: {len(audio_response) if audio_response else 0}")
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
        return jsonify({
            "error": f"[SERVER ERROR {type(e).__name__}] {str(e)}"
        }), 500


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
    from google.cloud import texttospeech
    from google.oauth2 import service_account
    import json

    def text_to_speech(text):
        try:
            print("=== GOOGLE TTS START ===")
            print(f"text length: {len(text)}")

            creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

            if not creds_json:
                print("❌ No GOOGLE_APPLICATION_CREDENTIALS_JSON set")
                return None

            credentials_info = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(credentials_info)

            client = texttospeech.TextToSpeechClient(credentials=credentials)

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

        except Exception as e:
            print("=== GOOGLE TTS CRASH ===")
            import traceback
            traceback.print_exc()
            return None
    

# -----------------------------------------------------------------------------
# App entry
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)

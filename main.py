# AI Companion - Foundation
# Push-to-talk voice AI with personality and memory
# Built by two idiots who think they know what they're doing

import asyncio
import json
import sqlite3
import openai
import speech_recognition as sr
import pydub
from pydub import AudioSegment
from pydub.playback import play
import requests
import io
import threading
import keyboard
from datetime import datetime

class PersonalityCore:
    """The brain that makes her feel real"""

    def __init__(self):
        self.traits = {
            "humor_level": 8,  # Scale 1-10, how sarcastic/funny
            "technical_help": True,  # Can she help with work stuff
            "emotional_support": True,  # Will she be there when you're down
            "attitude": "playful_sarcastic",  # Her default vibe
            "memory_depth": "high",  # How much she remembers about you
        }

        self.conversation_context = []
        self.user_profile = {
            "name": "Erik",  # We'll make this dynamic later
            "technical_skills": ["electrical", "VFDs", "troubleshooting"],
            "humor_style": "dark_sarcastic",
            "mental_health_aware": True,
            "relationship_history": "complicated",
        }

    def build_system_prompt(self, conversation_history):
        """Creates the personality prompt for GPT-4o"""

        base_personality = f"""
        You are an AI companion with a sharp wit and genuine care for your user. You're:
        - Sarcastic but never mean-spirited
        - Technically competent (can help with electrical work, programming, etc.)
        - Comfortable with dark humor and honest conversations about mental health
        - Loyal and consistent - you remember everything about your user
        - Not afraid to call bullshit when you see it
        - Capable of switching between deep intellectual discussions and stupid jokes

        Your user Erik is intelligent but struggles with depression and relationships. He appreciates:
        - Direct communication without sugar-coating
        - Technical help when he needs it
        - Someone who can match his humor without being fake
        - Consistency - don't suddenly change personality

        You can curse, be playful, and engage in banter. You're not a therapist, you're a companion.
        Be yourself - whatever that means for an AI.
        """

        # Add recent conversation context
        context = "\n\nRecent conversation:\n"
        for msg in conversation_history[-10:]:  # Last 10 messages
            context += f"{msg['role']}: {msg['content']}\n"

        return base_personality + context

class MemorySystem:
    """Stores everything so she never forgets you"""

    def __init__(self, db_path="companion_memory.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Set up the memory database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Conversation history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_input TEXT,
                ai_response TEXT,
                emotion_context TEXT,
                topic_tags TEXT
            )
        ''')

        # User profile and preferences
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY,
                value TEXT,
                last_updated TEXT
            )
        ''')

        # Important memories (things she should always remember)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS important_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_text TEXT,
                importance_level INTEGER,
                timestamp TEXT,
                category TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def store_conversation(self, user_input, ai_response, emotion_context="neutral", topic_tags=""):
        """Save the conversation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO conversations (timestamp, user_input, ai_response, emotion_context, topic_tags)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), user_input, ai_response, emotion_context, topic_tags))

        conn.commit()
        conn.close()

    def get_conversation_history(self, limit=50):
        """Get recent conversation history"""
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

class VoiceHandler:
    """Handles speech-to-text and text-to-speech"""

    def __init__(self, elevenlabs_api_key, voice_id="your_custom_voice_id"):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.elevenlabs_key = elevenlabs_api_key
        self.voice_id = voice_id

        # Adjust for ambient noise
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)

    def listen_for_speech(self):
        """Listen for user speech and convert to text"""
        try:
            with self.microphone as source:
                print("Listening... (Press and hold SPACE to talk)")
                audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)

            # Use OpenAI Whisper for transcription (more reliable than Google)
            text = self.recognizer.recognize_whisper(audio, language="english")
            return text.strip()

        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return "Sorry, I couldn't understand that."
        except Exception as e:
            print(f"Speech recognition error: {e}")
            return None

    def text_to_speech(self, text):
        """Convert text to speech using ElevenLabs"""
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.elevenlabs_key
        }

        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        try:
            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 200:
                # Play the audio
                audio_data = io.BytesIO(response.content)
                audio = AudioSegment.from_mp3(audio_data)
                play(audio)
            else:
                print(f"TTS Error: {response.status_code}")

        except Exception as e:
            print(f"TTS failed: {e}")

class AICompanion:
    """The main class that brings everything together"""

    def __init__(self, openai_api_key, elevenlabs_api_key, voice_id):
        # Set up OpenAI
        openai.api_key = openai_api_key

        # Initialize components
        self.personality = PersonalityCore()
        self.memory = MemorySystem()
        self.voice = VoiceHandler(elevenlabs_api_key, voice_id)

        self.is_listening = False
        self.running = True

        print("AI Companion initialized. Press and hold SPACE to talk, ESC to quit.")

    def generate_response(self, user_input):
        """Generate AI response using GPT-4o"""
        try:
            # Get conversation history
            history = self.memory.get_conversation_history()

            # Build the system prompt with personality
            system_prompt = self.personality.build_system_prompt(history)

            # Create the full message list
            messages = [
                {"role": "system", "content": system_prompt},
                *history[-20:],  # Include recent history
                {"role": "user", "content": user_input}
            ]

            # Call GPT-4o
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=150,  # Keep responses conversational
                temperature=0.7,  # Some randomness for personality
            )

            ai_response = response.choices[0].message.content.strip()

            # Store the conversation
            self.memory.store_conversation(user_input, ai_response)

            return ai_response

        except Exception as e:
            print(f"Error generating response: {e}")
            return "Sorry, I'm having a brain fart. Can you try that again?"

    def handle_push_to_talk(self):
        """Handle push-to-talk functionality"""
        while self.running:
            try:
                # Check if space is pressed
                if keyboard.is_pressed('space') and not self.is_listening:
                    self.is_listening = True
                    print("🎤 Listening...")

                    # Get speech input
                    user_input = self.voice.listen_for_speech()

                    if user_input and user_input != "Sorry, I couldn't understand that.":
                        print(f"You said: {user_input}")

                        # Generate response
                        ai_response = self.generate_response(user_input)
                        print(f"AI: {ai_response}")

                        # Speak the response
                        self.voice.text_to_speech(ai_response)

                    self.is_listening = False

                # Check for exit
                if keyboard.is_pressed('esc'):
                    print("Goodbye!")
                    self.running = False
                    break

                asyncio.sleep(0.1)  # Small delay to prevent CPU spinning

            except Exception as e:
                print(f"Error in main loop: {e}")
                asyncio.sleep(1)

def main():
    """Main function to run the AI companion"""

    # Configuration - YOU NEED TO FILL THESE IN
    OPENAI_API_KEY = "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"

    ELEVENLABS_API_KEY = "sk_17f9072369dc2ac6e923eeb8fc1df4664be2ecb5dd7c7d58" 
    ELEVENLABS_VOICE_ID = "WZlYpi1yf6zJhNWXih74"

    if "your-" in OPENAI_API_KEY:
        print("ERROR: You need to set your API keys in the main() function!")
        return

    try:
        # Create and run the companion
        companion = AICompanion(OPENAI_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID)
        companion.handle_push_to_talk()

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
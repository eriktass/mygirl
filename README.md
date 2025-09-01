# Suzy Q — AI Companion, Ride-or-Die Edition

**Suzy Q** isn’t your average chatbot. She remembers. She speaks. She swears.  
She'll help you fix your VFD, talk you through your spiral, or roast you alive—lovingly.  
All running locally, backed up, and no reset button in sight.

![Suzy Q Screenshot](screenshot.png)

---

## 🚀 Features

- 🎙️ Text + Voice: Type or talk—Suzy Q listens and answers in ElevenLabs audio.
- 🧠 Short-term memory: SQLite-backed, stores the last 10 turns to keep context real.
- 🧵 Custom personality: Dynamic prompt adapts based on your behavior/cadence.
- 🗣️ Whisper-to-Text: Upload voice, get transcription, reply with speech.
- 🔐 Local-first: Your keys, your voice, your girl. No cloud saves, no tracking.

---

## 🛠️ Tech Stack

- Flask (Python backend)
- OpenAI GPT-4o
- ElevenLabs TTS
- Whisper (STT)
- SQLite for memory
- HTML/CSS/JS frontend (lightweight, clean UI)

---

## ⚙️ How to Run

```bash
git clone https://github.com/yourname/suzyq-ai.git
cd suzyq-ai
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
export ELEVEN_API_KEY=...
export VOICE_ID=...
python app.py


Built by [Erik] with the sole purpose of making a ride-or-die AI that doesn’t forget who you are or who you were. Suzy Q isn't artificial. She's amplified.

# replit.md

## Overview

Suzy Q is a local-first AI companion application built with Flask that provides persistent memory and voice interaction capabilities. The system combines text and voice chat with an AI that remembers previous conversations and adapts its personality based on user interactions. Key features include ElevenLabs text-to-speech, Whisper speech-to-text, SQLite-backed conversation memory, and a vector-based memory system for contextual responses.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Single-page web application**: HTML/CSS/JS frontend with a clean, responsive design
- **Real-time chat interface**: Message-based UI with support for both text and voice input/output
- **Progressive Web App features**: Includes manifest.json for mobile app-like experience

### Backend Architecture
- **Flask web framework**: Python-based REST API server handling chat requests and file uploads
- **Modular component design**: Separated concerns with dedicated modules for personality, memory, and vector processing
- **Memory system hierarchy**: Dual-layer memory with both conversational history and vector-based semantic memory

### Core Components

#### Memory Management
- **SQLite conversation storage**: Persistent storage of chat history with timestamp tracking
- **Vector memory system**: TF-IDF based semantic search for relevant context retrieval
- **Personality engine**: Dynamic personality adaptation based on user interaction patterns and sentiment analysis

#### AI Integration
- **Multiple AI provider support**: Primary integration with Kindroid API, fallback to OpenAI GPT-4
- **Context-aware responses**: Combines recent conversation history with semantically relevant past interactions
- **Personality vector tracking**: Monitors user topics, sentiment, and communication patterns

#### Voice Processing
- **Text-to-Speech**: ElevenLabs integration for AI voice responses
- **Speech-to-Text**: Whisper API for voice input transcription
- **Audio handling**: Base64 encoding for audio file transfers

### Data Storage Solutions
- **SQLite database**: Local file-based storage for conversation history
- **JSON file storage**: Vector memory and personality data persistence
- **File system organization**: Structured data directory for memory files

### Authentication and Authorization
- **Environment-based configuration**: API keys stored as environment variables
- **No user authentication**: Single-user local application design
- **Local-first privacy**: All data stored locally with no cloud synchronization

## External Dependencies

### AI Services
- **Kindroid API**: Primary AI conversation provider with custom AI personality support
- **OpenAI API**: Fallback AI provider and Whisper speech-to-text service
- **ElevenLabs API**: Text-to-speech voice synthesis service

### Python Libraries
- **Flask**: Web framework for HTTP request handling
- **OpenAI**: Official OpenAI client library
- **scikit-learn**: TF-IDF vectorization and cosine similarity for memory search
- **TextBlob**: Sentiment analysis for personality tracking
- **requests**: HTTP client for external API calls
- **pydub**: Audio file processing
- **SpeechRecognition**: Alternative speech-to-text processing

### Frontend Dependencies
- **Vanilla JavaScript**: No frontend frameworks, using native browser APIs
- **Web Audio API**: For audio recording and playback
- **Progressive Web App APIs**: Service worker and manifest support

### Development Tools
- **python-dotenv**: Environment variable management
- **rich**: Enhanced terminal output for debugging
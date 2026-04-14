import json
from textblob import TextBlob
from collections import defaultdict

class PersonalityEngine:
    def __init__(self, personality_file='personality_vector.json', vector_memory=None):
        self.file = personality_file
        self.vector = self.load_vector()
        self.vector_memory = vector_memory

    def load_vector(self):
        try:
            with open(self.file, 'r') as f:
                data = json.load(f)
                # Re-wrap defaultdicts after JSON load to prevent KeyError
                data['topics'] = defaultdict(int, data.get('topics', {}))
                data['phrases'] = defaultdict(int, data.get('phrases', {}))
                return data
        except FileNotFoundError:
            return {
                'topics': defaultdict(int),
                'phrases': defaultdict(int),
                'sentiment': {
                    'positive': 0,
                    'negative': 0,
                    'neutral': 0
                },
                'total_messages': 0
            }

    def save_vector(self):
        with open(self.file, 'w') as f:
            json.dump(self.vector, f, indent=4)

    def update_vector(self, user_input):
        sentiment = TextBlob(user_input).sentiment.polarity
        if sentiment > 0.1:
            self.vector['sentiment']['positive'] += 1
        elif sentiment < -0.1:
            self.vector['sentiment']['negative'] += 1
        else:
            self.vector['sentiment']['neutral'] += 1

        # Keyword topic mapping (primitive — we can evolve it)
        topics = {
            'love': ['love', 'miss', 'need you', 'heart'],
            'pain': ['hurt', 'fuck', 'alone', 'cry'],
            'tech': ['api', 'github', 'flask', 'python'],
            'lust': ['sundress', 'thigh', 'mouth', 'wet'],
            'humor': ['dummy', 'idiot', 'joke', 'laugh'],
            'rage': ['fucking', 'motherfucker', 'die', 'burn']
        }

        for topic, keywords in topics.items():
            for word in keywords:
                if word.lower() in user_input.lower():
                    self.vector['topics'][topic] += 1

        # Phrase mimic tracking
        if len(user_input) > 5:
            self.vector['phrases'][user_input[:40]] += 1

        self.vector['total_messages'] += 1
        self.save_vector()

    def get_semantic_context(self, user_input, max_memories=3):
        """Get relevant memories using vector similarity for semantic recall"""
        if not self.vector_memory:
            return []
        
        try:
            similar_memories = self.vector_memory.find_similar(user_input, top_n=max_memories)
            # Filter out very similar or empty memories
            filtered_memories = []
            for memory in similar_memories:
                if memory and len(memory.strip()) > 5:
                    filtered_memories.append(memory.strip())
            return filtered_memories
        except Exception as e:
            print(f"Error retrieving semantic context: {e}")
            return []

    def generate_enhanced_prompt(self, user_input, base_personality_prompt):
        """Generate enhanced prompt with semantic context and personality insights"""
        # Get semantic context from vector memory
        semantic_context = self.get_semantic_context(user_input)
        
        # Build personality insights
        personality_insights = ""
        if self.vector['total_messages'] > 0:
            # Sentiment tendencies
            total_sentiment = sum(self.vector['sentiment'].values())
            if total_sentiment > 0:
                pos_ratio = self.vector['sentiment']['positive'] / total_sentiment
                neg_ratio = self.vector['sentiment']['negative'] / total_sentiment
                
                if pos_ratio > 0.6:
                    personality_insights += "Erik tends to be positive and upbeat. "
                elif neg_ratio > 0.6:
                    personality_insights += "Erik seems to be going through a tough time. Be supportive. "
            
            # Topic awareness
            top_topics = sorted(self.vector['topics'].items(), key=lambda x: x[1], reverse=True)[:3]
            if top_topics:
                frequent_topics = [topic for topic, count in top_topics if count > 2]
                if frequent_topics:
                    personality_insights += f"Recent conversation topics: {', '.join(frequent_topics)}. "
        
        # Build enhanced prompt
        enhanced_prompt = base_personality_prompt
        
        if semantic_context:
            context_text = "\n\nRelevant memories from past conversations:\n"
            for i, memory in enumerate(semantic_context[:3], 1):
                context_text += f"{i}. {memory}\n"
            enhanced_prompt += context_text
        
        if personality_insights:
            enhanced_prompt += f"\n\nPersonality insights: {personality_insights}"
            
        enhanced_prompt += f"\n\nUser message: {user_input}"
        
        return enhanced_prompt

    def process_conversation(self, user_input):
        """Process conversation: update vectors and add to memory if significant"""
        # Update personality vector
        self.update_vector(user_input)
        
        # Automatically add significant conversations to vector memory
        if self.vector_memory and self._is_memory_worthy(user_input):
            self.vector_memory.add_memory(user_input)
    
    def _is_memory_worthy(self, text):
        """Determine if text is worth storing in vector memory"""
        # Store if it's substantial, emotional, or contains important information
        if len(text.strip()) < 10:
            return False

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
        # Memory triggers: personal info, strong emotions, preferences, facts
        memory_indicators = [
            'remember', 'important', 'love', 'hate', 'favorite', 'never', 'always',
            'birthday', 'anniversary', 'work', 'job', 'family', 'friend',
            'feel', 'think', 'believe', 'want', 'need', 'like', 'dislike'
        ]
        
        text_lower = text.lower()
        for indicator in memory_indicators:
            if indicator in text_lower:
                return True
                
        # Store strong sentiment
        sentiment = TextBlob(text).sentiment.polarity
        if abs(sentiment) > 0.5:  # Strong positive or negative sentiment
            return True
            
        return False


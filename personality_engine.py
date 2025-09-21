import json
from textblob import TextBlob
from collections import defaultdict

class PersonalityEngine:
    def __init__(self, personality_file='personality_vector.json'):
        self.file = personality_file
        self.vector = self.load_vector()

    def load_vector(self):
        try:
            with open(self.file, 'r') as f:
                return json.load(f)
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

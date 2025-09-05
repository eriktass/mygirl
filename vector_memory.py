import json
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class VectorMemory:
    def __init__(self, memory_file="data/vector_mem.json"):
        self.memory_file = memory_file
        self.entries = self.load_memory()

    def load_memory(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r") as f:
                return json.load(f)
        return []

    def save_memory(self):
        # 🔥 THIS CREATES THE data/ FOLDER IF MISSING
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, "w") as f:
            json.dump(self.entries, f, indent=2)

    def add_memory(self, text):
        self.entries.append(text)
        self.save_memory()

    def find_similar(self, query, top_n=3):
        all_text = self.entries + [query]
        vectorizer = TfidfVectorizer()
        vectors = vectorizer.fit_transform(all_text)
        similarity_matrix = cosine_similarity(vectors[-1:], vectors[:-1])
        sorted_indices = similarity_matrix[0].argsort()[::-1][:top_n]
        return [self.entries[i] for i in sorted_indices]

import json
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class VectorMemory:
    def __init__(self, memory_file="data/vector_memory.json"):
        self.memory_file = memory_file
        self.entries = self.load_memory()

    def load_memory(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save_memory(self):
        # Create the data/ folder if it doesn't exist
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2)

    def add_memory(self, text):
        # Avoid storing empty values
        if not text or not text.strip():
            return

        self.entries.append(text.strip())
        self.save_memory()

    def find_similar(self, query, top_n=3):
        # Handle edge case: no stored entries
        if not self.entries:
            return []

        # Build corpus with stored entries + current query
        all_text = self.entries + [query]

        vectorizer = TfidfVectorizer()
        vectors = vectorizer.fit_transform(all_text)

        # Compare the query (last item) against all stored entries
        similarity_matrix = cosine_similarity(vectors[-1:], vectors[:-1])
        sorted_indices = similarity_matrix[0].argsort()[::-1][:top_n]

        return [self.entries[i] for i in sorted_indices]

    def search_memories(self, query, max_items=3):
        return self.find_similar(query, top_n=max_items)

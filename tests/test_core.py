"""Tests for the core pipeline components."""

from __future__ import annotations

from kimiko.core.intent import IntentClassifier
from kimiko.core.ranking import RetrievalRanker
from kimiko.core.token_manager import TokenManager
from kimiko.models.schemas import Intent, Message, Role


class TestIntentClassifier:
    """Tests for the rule-based intent classifier."""

    def setup_method(self):
        self.classifier = IntentClassifier()

    def test_greeting_intent(self):
        result = self.classifier.classify("Hello there!")
        assert result.intent == Intent.GREETING

    def test_code_intent(self):
        result = self.classifier.classify("Write a Python function to sort a list")
        assert result.intent == Intent.CODE

    def test_question_intent(self):
        result = self.classifier.classify("What is machine learning?")
        assert result.intent == Intent.QUESTION

    def test_default_chat(self):
        result = self.classifier.classify("random gibberish xyz")
        assert result.intent == Intent.CHAT

    def test_confidence_range(self):
        result = self.classifier.classify("Explain recursion to me")
        assert 0.0 <= result.confidence <= 1.0


class TestTokenManager:
    """Tests for token budgeting and truncation."""

    def setup_method(self):
        self.tm = TokenManager()

    def test_count_tokens(self):
        text = "Hello world"
        tokens = self.tm.count_tokens(text)
        assert tokens > 0

    def test_truncate_messages_keeps_last(self):
        messages = [
            Message(role=Role.USER, content="first message " * 100),
            Message(role=Role.USER, content="second message " * 100),
            Message(role=Role.USER, content="last message"),
        ]
        truncated = self.tm.truncate_messages(messages, max_tokens=50)
        assert len(truncated) > 0
        assert truncated[-1].content == "last message"

    def test_get_budget_known_model(self):
        budget = self.tm.get_budget("qwen2.5")
        assert "system" in budget
        assert "history" in budget

    def test_get_budget_unknown_model(self):
        budget = self.tm.get_budget("unknown-model")
        assert "system" in budget  # Falls back to default

    def test_allocate_budget(self):
        budget = self.tm.allocate_budget("qwen2.5")
        assert "system" in budget
        assert "context_window" not in budget  # Window is popped

    def test_truncate_text(self):
        long_text = "x" * 10000
        truncated = self.tm.truncate_text(long_text, max_tokens=10)
        assert len(truncated) < len(long_text)


class TestRetrievalRanker:
    """Tests for hybrid retrieval ranking."""

    def setup_method(self):
        self.ranker = RetrievalRanker()

    def test_rank_by_semantic_score(self):
        import time
        results = [
            {"text": "low score", "score": 0.3, "metadata": {"timestamp": time.time(), "tags": []}},
            {"text": "high score", "score": 0.9, "metadata": {"timestamp": time.time(), "tags": []}},
        ]
        ranked = self.ranker.rank(results)
        assert ranked[0]["text"] == "high score"

    def test_recency_decay(self):
        import time
        recent = time.time()
        old = time.time() - 30 * 24 * 3600  # 30 days ago

        assert self.ranker.compute_recency_score(recent) > self.ranker.compute_recency_score(old)

    def test_tag_matching(self):
        score = self.ranker.compute_tag_match_score(
            ["python", "ai"], ["python", "robotics"]
        )
        assert 0.0 < score < 1.0

    def test_empty_results(self):
        ranked = self.ranker.rank([])
        assert ranked == []

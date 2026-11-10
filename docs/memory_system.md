# 🧠 Kimiko Memory System

Kimiko uses a sophisticated, multi-tiered memory architecture to achieve "True Persistence" — the ability to remember your preferences and life facts indefinitely without context bloat.

## 🏗️ The Tiers

| Tier | Duration | Technology | Purpose |
|------|----------|------------|---------|
| **Short-Term** | Recent | Redis / RAM | Fluid chat history (last 5-10 messages). |
| **Middle-Term** | Contextual | Qdrant | Semantic retrieval of "similar" past knowledge. |
| **Long-Term** | Indefinite | PostgreSQL | Structured facts (Identity, Preferences, Habits). |

---

## 💎 Fact Extraction (The Intelligence Layer)

Unlike standard RAG, Kimiko doesn't just store what you say; it understands it.

1. **Extraction**: While you chat, a background worker analyzes messages for "Knowledge Points."
2. **Structured Storage**: Facts are stored in the `user_facts` table with categories (e.g., `hobby`, `work`, `preference`).
3. **Confidence Scoring**: Each fact starts with a confidence level based on LLM certainty.

---

## 📉 Memory Decay & Reinforcement

To prevent "stale" or "bloated" memory, Kimiko uses a human-inspired reinforcement model:

- **Exponential Decay**: `confidence = confidence * exp(-decay_rate * days_since_seen)`.
- **Reinforcement**: Mentioning a fact again resets its decay and increases its importance.
- **Fact Floor**: Critical facts (like your name) have a confidence floor to prevent them from ever being forgotten.

---

## 🎯 Ranking & Retrieval

When you ask a question, the **Retrieval Engine**:
1. Pulls potential memories from all tiers.
2. The **Ranker** applies a hybrid score:
   - `0.05 * fact_confidence`: Prioritizes verified facts over random chat logs.
   - `1.5x Multiplier`: Applied to `identity` and `preference` categories.
3. The **Token Manager** then scales the history based on remaining context window room.

### Conflict Resolution Ordering

For contradictory memories/facts, Kimiko now applies deterministic recency ordering before prompt assembly:
- `last_seen` (newest first)
- `updated_at` (tiebreaker)
- `created_at` (final recency tiebreaker)
- For mutable preference statements (for example, `favorite ... is ...`), only the newest winner is kept in context and its confidence is preserved from the strongest matching candidate.

This prevents stale ties where an older fact (for example, "Python") could appear before a newer update (for example, "Rust").

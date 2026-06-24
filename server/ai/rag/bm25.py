"""BM25 sparse retrieval with Chinese tokenization support.

Provides a lightweight BM25 scorer that can be paired with ChromaDB dense
retrieval for hybrid search. Uses jieba for Chinese text when available,
falling back to character bigrams.
"""

import math
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Try jieba for Chinese word segmentation; fall back to character bigrams.
try:
    import jieba

    _JIEBA_AVAILABLE = True
except ImportError:
    _JIEBA_AVAILABLE = False
    logger.info("jieba not installed — using character bigram tokenization for BM25")


def _tokenize(text: str) -> list[str]:
    """Tokenize text for BM25 indexing.

    Uses jieba for Chinese-dominant text; falls back to character bigrams +
    whitespace splitting for mixed Latin/CJK content.
    """
    if not text or not text.strip():
        return []

    if _JIEBA_AVAILABLE:
        # jieba.cut returns a generator — collect into list
        tokens = list(jieba.cut(text))
        # Filter out whitespace-only tokens
        return [t.strip() for t in tokens if t.strip()]
    else:
        # Fallback: character bigrams for CJK + whitespace tokens for Latin
        tokens = []
        # Split on whitespace first
        parts = text.lower().split()
        for part in parts:
            # If the part contains CJK characters, generate bigrams
            if any('一' <= c <= '鿿' or '぀' <= c <= 'ヿ' for c in part):
                # Also preserve single chars as unigrams for better recall
                tokens.append(part[0]) if len(part) >= 1 else None
                for i in range(len(part) - 1):
                    tokens.append(part[i : i + 2])
                tokens.append(part[-1]) if len(part) >= 2 else None
            else:
                tokens.append(part)
        return tokens


class BM25Index:
    """BM25 (Okapi BM25) scoring index for a fixed corpus of documents.

    Typical usage::

        index = BM25Index(documents)
        results = index.search("Redis 缓存", k=5)
        # → [(doc_index, bm25_score), ...]
    """

    def __init__(
        self,
        corpus: list[str],
        k1: float = 1.5,
        b: float = 0.75,
    ):
        """Build the BM25 index over *corpus*.

        Args:
            corpus: List of document strings.
            k1: Term frequency saturation parameter (default 1.5).
            b: Length normalization parameter (default 0.75).
        """
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self._doc_count = len(corpus)

        # Tokenize every document
        self._tokenized: list[list[str]] = [_tokenize(doc) for doc in corpus]

        # Average document length (in tokens)
        total_len = sum(len(t) for t in self._tokenized)
        self._avgdl = total_len / max(1, self._doc_count)

        # Compute document frequency for every term
        df: Counter[str] = Counter()
        for tokens in self._tokenized:
            for term in set(tokens):
                df[term] += 1

        # IDF (inverse document frequency) — smoothed
        self._idf: dict[str, float] = {}
        for term, freq in df.items():
            self._idf[term] = math.log(
                1.0 + (self._doc_count - freq + 0.5) / (freq + 0.5)
            )

        # Cache per-document term frequencies for fast scoring
        self._tf_cache: list[Counter[str]] = [Counter(t) for t in self._tokenized]

        logger.debug(
            "BM25 index built: %d docs, avg_len=%.1f tokens, vocab=%d terms",
            self._doc_count,
            self._avgdl,
            len(self._idf),
        )

    @property
    def doc_count(self) -> int:
        return self._doc_count

    def _score_one(self, doc_idx: int, query_tokens: list[str]) -> float:
        """Compute BM25 score for a single document against query tokens."""
        if doc_idx >= self._doc_count:
            return 0.0

        doc_len = len(self._tokenized[doc_idx])
        if doc_len == 0:
            return 0.0

        tf_counts = self._tf_cache[doc_idx]
        score = 0.0

        for token in query_tokens:
            idf = self._idf.get(token, 0.0)
            if idf == 0.0:
                continue
            tf = tf_counts.get(token, 0)
            if tf == 0:
                continue
            numerator = tf * (self.k1 + 1.0)
            denominator = tf + self.k1 * (
                1.0 - self.b + self.b * doc_len / self._avgdl
            )
            score += idf * numerator / denominator

        return score

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        """Return top-*k* (document_index, bm25_score) for *query*.

        Only documents with a non-zero score are returned.
        """
        if not query or not query.strip() or self._doc_count == 0:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # Score every document (for small corpuses this is fine; for large
        # production systems an inverted-index-based top-k retrieval with
        # early termination would be preferable).
        scored = []
        for idx in range(self._doc_count):
            s = self._score_one(idx, query_tokens)
            if s > 0:
                scored.append((idx, s))

        # Sort descending by score
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def get_document(self, idx: int) -> str:
        """Return the raw text of document *idx*."""
        if 0 <= idx < self._doc_count:
            return self.corpus[idx]
        return ""

"""Optional embedding-based RAG (sentence-transformers). Falls back if unavailable."""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from testbench.rag import (
    RagConfig,
    RagHit,
    _make_snippet,
    _read_text_file,
    _resolve_dir,
    _split_into_chunks,
    _tokenize,
)

_EMBED_LOCK = threading.Lock()
_EMBED_MODEL_CACHE: Dict[str, Any] = {}


def embeddings_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _load_model(model_name: str):
    with _EMBED_LOCK:
        if model_name in _EMBED_MODEL_CACHE:
            return _EMBED_MODEL_CACHE[model_name]
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        _EMBED_MODEL_CACHE[model_name] = model
        return model


class EmbeddingRagIndex:
    """Semantic retrieval over the same chunked corpus as TF–IDF RAG."""

    def __init__(self, root: Path, rag_cfg: RagConfig):
        self.root = Path(root).resolve()
        self.cfg = rag_cfg
        self._texts: List[str] = []
        self._meta: List[Tuple[str, int]] = []
        self._vectors: Any = None
        self._signature: Tuple = tuple()
        self._model_name = rag_cfg.embedding_model or "all-MiniLM-L6-v2"
        self._build()

    @property
    def chunk_count(self) -> int:
        return len(self._texts)

    @property
    def file_count(self) -> int:
        return len({m[0] for m in self._meta})

    def _iter_files(self):
        if not self.root.is_dir():
            return []
        out = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.suffix.lower() in self.cfg.extensions:
                out.append(path)
        return out

    def signature(self) -> Tuple:
        sig = []
        for p in self._iter_files():
            try:
                st = p.stat()
                sig.append((str(p.relative_to(self.root)).replace("\\", "/"), int(st.st_mtime_ns), int(st.st_size)))
            except OSError:
                continue
        return tuple(sig)

    def _build(self) -> None:
        texts: List[str] = []
        meta: List[Tuple[str, int]] = []
        for path in self._iter_files():
            text = _read_text_file(path)
            if not text.strip():
                continue
            try:
                rel = str(path.relative_to(self.root)).replace("\\", "/")
            except ValueError:
                rel = path.name
            for idx, chunk in enumerate(_split_into_chunks(text, self.cfg.chunk_chars, self.cfg.chunk_overlap)):
                if chunk.strip():
                    texts.append(chunk)
                    meta.append((rel, idx))

        self._texts = texts
        self._meta = meta
        self._signature = self.signature()

        if not texts:
            self._vectors = None
            return

        model = _load_model(self._model_name)
        self._vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    def is_stale(self) -> bool:
        return self.signature() != self._signature

    def reload(self) -> None:
        self._build()

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[RagHit]:
        if self._vectors is None or not self._texts:
            return []
        k = max(1, int(top_k or self.cfg.top_k))
        model = _load_model(self._model_name)
        qv = model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        scored: List[Tuple[float, int]] = []
        for i, dv in enumerate(self._vectors):
            dot = float(sum(a * b for a, b in zip(qv, dv)))
            scored.append((dot, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        q_tokens = _tokenize(query)
        hits: List[RagHit] = []
        for score, idx in scored[:k]:
            rel, cidx = self._meta[idx]
            text = self._texts[idx]
            hits.append(
                RagHit(
                    rel_path=rel,
                    chunk_index=cidx,
                    score=float(score),
                    snippet=_make_snippet(text, q_tokens),
                    text=text,
                )
            )
        return hits

"""Lightweight retrieval-augmented generation (RAG) over a local docs folder.

Zero extra dependencies: builds a TF–IDF index over chunked text/markdown/json
files using only the Python standard library. Suitable for tens of thousands
of small chunks; switch to a vector DB if your corpus grows much larger.

Public API:

- :class:`RagConfig` — reads ``cfg["rag"]`` from the bench JSON.
- :func:`get_index(cfg, root=None)` — returns a cached :class:`RagIndex`,
  rebuilt automatically when files in the docs folder change.
- :class:`RagIndex.retrieve(query, top_k)` — top hits with a snippet preview.
- :func:`format_context_for_prompt(hits, max_chars)` — compact text block
  to inject into an LLM prompt.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from testbench._paths import repo_root


_DEFAULT_DIR = "rag_docs"
_DEFAULT_EXTS = (".txt", ".md", ".markdown", ".rst", ".json", ".csv", ".log", ".py")
_DEFAULT_TOP_K = 4
_DEFAULT_CHUNK_CHARS = 800
_DEFAULT_CHUNK_OVERLAP = 120
_DEFAULT_MAX_CONTEXT_CHARS = 4000
_MAX_FILE_BYTES = 2_000_000


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")
_STOPWORDS = frozenset(
    """
    the a an and or but if then else of in on at to for with by from as is are was were be been being
    this that these those it its as not no into out over under between within without about up down
    we you they i he she them us our your their his her my mine yours theirs ours
    do does did done doing can could should would may might must will shall have has had having
    so than too very also which what who whom whose where when why how
    """.split()
)


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if t.lower() not in _STOPWORDS]


@dataclass(frozen=True)
class RagConfig:
    enabled: bool = True
    dir: str = _DEFAULT_DIR
    extensions: Tuple[str, ...] = _DEFAULT_EXTS
    top_k: int = _DEFAULT_TOP_K
    chunk_chars: int = _DEFAULT_CHUNK_CHARS
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP
    max_context_chars: int = _DEFAULT_MAX_CONTEXT_CHARS

    @classmethod
    def from_config(cls, cfg: Optional[Dict[str, Any]]) -> "RagConfig":
        rag = (cfg or {}).get("rag") if isinstance(cfg, dict) else None
        if not isinstance(rag, dict):
            return cls()
        exts = rag.get("extensions") or _DEFAULT_EXTS
        if isinstance(exts, (list, tuple)):
            cleaned = []
            for e in exts:
                s = str(e).strip().lower()
                if not s:
                    continue
                if not s.startswith("."):
                    s = "." + s
                cleaned.append(s)
            exts_t = tuple(cleaned) or _DEFAULT_EXTS
        else:
            exts_t = _DEFAULT_EXTS

        def _int(key: str, default: int, lo: int, hi: int) -> int:
            try:
                v = int(rag.get(key, default))
            except (TypeError, ValueError):
                v = default
            return max(lo, min(hi, v))

        return cls(
            enabled=bool(rag.get("enabled", True)),
            dir=str(rag.get("dir", _DEFAULT_DIR) or _DEFAULT_DIR),
            extensions=exts_t,
            top_k=_int("top_k", _DEFAULT_TOP_K, 1, 20),
            chunk_chars=_int("chunk_chars", _DEFAULT_CHUNK_CHARS, 200, 8000),
            chunk_overlap=_int("chunk_overlap", _DEFAULT_CHUNK_OVERLAP, 0, 4000),
            max_context_chars=_int("max_context_chars", _DEFAULT_MAX_CONTEXT_CHARS, 200, 32_000),
        )


@dataclass
class _Chunk:
    rel_path: str
    chunk_index: int
    text: str
    tokens: Counter = field(default_factory=Counter)
    length: int = 0


def _read_text_file(path: Path, max_bytes: int = _MAX_FILE_BYTES) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    if size > max_bytes:
        try:
            with path.open("rb") as f:
                raw = f.read(max_bytes)
            return raw.decode("utf-8", errors="replace") + f"\n...[truncated, {size - max_bytes} more bytes]"
        except OSError:
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _split_into_chunks(text: str, chunk_chars: int, overlap: int) -> List[str]:
    s = (text or "").strip()
    if not s:
        return []
    if len(s) <= chunk_chars:
        return [s]
    chunks: List[str] = []
    step = max(1, chunk_chars - overlap)
    i = 0
    n = len(s)
    while i < n:
        end = min(n, i + chunk_chars)
        if end < n:
            window = s[i:end]
            cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "))
            if cut > int(chunk_chars * 0.5):
                end = i + cut + 1
        chunks.append(s[i:end].strip())
        if end >= n:
            break
        i = max(end - overlap, i + step)
    return [c for c in chunks if c]


@dataclass
class RagHit:
    rel_path: str
    chunk_index: int
    score: float
    snippet: str
    text: str


class RagIndex:
    """In-memory TF–IDF index over a local folder.

    Use :func:`get_index` to obtain a cached instance that auto-refreshes when
    files in the docs folder change.
    """

    def __init__(self, root: Path, rag_cfg: RagConfig):
        self.root = Path(root).resolve()
        self.cfg = rag_cfg
        self._chunks: List[_Chunk] = []
        self._df: Counter = Counter()
        self._idf: Dict[str, float] = {}
        self._signature: Tuple[Tuple[str, int, int], ...] = tuple()
        self._build()

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def file_count(self) -> int:
        return len({c.rel_path for c in self._chunks})

    def _iter_files(self) -> Iterable[Path]:
        if not self.root.is_dir():
            return []
        out: List[Path] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.cfg.extensions:
                continue
            out.append(path)
        return out

    def signature(self) -> Tuple[Tuple[str, int, int], ...]:
        sig: List[Tuple[str, int, int]] = []
        for p in self._iter_files():
            try:
                st = p.stat()
                sig.append((str(p.relative_to(self.root)).replace("\\", "/"), int(st.st_mtime_ns), int(st.st_size)))
            except OSError:
                continue
        return tuple(sig)

    def _build(self) -> None:
        chunks: List[_Chunk] = []
        df: Counter = Counter()

        for path in self._iter_files():
            text = _read_text_file(path)
            if not text.strip():
                continue
            try:
                rel = str(path.relative_to(self.root)).replace("\\", "/")
            except ValueError:
                rel = path.name
            for idx, chunk in enumerate(_split_into_chunks(text, self.cfg.chunk_chars, self.cfg.chunk_overlap)):
                tokens = _tokenize(chunk)
                if not tokens:
                    continue
                tf = Counter(tokens)
                ch = _Chunk(rel_path=rel, chunk_index=idx, text=chunk, tokens=tf, length=len(tokens))
                chunks.append(ch)
                for tok in tf.keys():
                    df[tok] += 1

        n_docs = len(chunks) or 1
        idf: Dict[str, float] = {tok: math.log((1 + n_docs) / (1 + freq)) + 1.0 for tok, freq in df.items()}

        self._chunks = chunks
        self._df = df
        self._idf = idf
        self._signature = self.signature()

    def is_stale(self) -> bool:
        return self.signature() != self._signature

    def reload(self) -> None:
        self._build()

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[RagHit]:
        if not self._chunks:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        q_tf = Counter(q_tokens)
        q_vec = {tok: tf * self._idf.get(tok, 0.0) for tok, tf in q_tf.items()}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        k = max(1, int(top_k or self.cfg.top_k))
        scored: List[Tuple[float, _Chunk]] = []
        for ch in self._chunks:
            if not any(tok in ch.tokens for tok in q_vec):
                continue
            doc_norm_sq = 0.0
            dot = 0.0
            for tok, tf in ch.tokens.items():
                w = tf * self._idf.get(tok, 0.0)
                doc_norm_sq += w * w
                qw = q_vec.get(tok)
                if qw:
                    dot += w * qw
            if dot <= 0:
                continue
            doc_norm = math.sqrt(doc_norm_sq) or 1.0
            score = dot / (q_norm * doc_norm)
            scored.append((score, ch))

        scored.sort(key=lambda x: x[0], reverse=True)
        hits: List[RagHit] = []
        for score, ch in scored[:k]:
            snippet = _make_snippet(ch.text, q_tokens, max_chars=240)
            hits.append(
                RagHit(
                    rel_path=ch.rel_path,
                    chunk_index=ch.chunk_index,
                    score=float(score),
                    snippet=snippet,
                    text=ch.text,
                )
            )
        return hits


def _make_snippet(text: str, query_tokens: Iterable[str], max_chars: int = 240) -> str:
    s = text or ""
    lower = s.lower()
    pos = -1
    for tok in query_tokens:
        if not tok:
            continue
        i = lower.find(tok)
        if i >= 0 and (pos < 0 or i < pos):
            pos = i
    if pos < 0:
        snippet = s[:max_chars]
    else:
        start = max(0, pos - max_chars // 3)
        end = min(len(s), start + max_chars)
        snippet = s[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(s):
            snippet = snippet + "…"
    return re.sub(r"\s+", " ", snippet).strip()


def format_context_for_prompt(hits: List[RagHit], max_chars: Optional[int] = None) -> str:
    """Render retrieved chunks as a compact ``CONTEXT:`` block for LLM prompts."""
    if not hits:
        return ""
    budget = max(200, int(max_chars or _DEFAULT_MAX_CONTEXT_CHARS))
    lines: List[str] = []
    used = 0
    for i, h in enumerate(hits, 1):
        header = f"[{i}] {h.rel_path} (chunk #{h.chunk_index}, score={h.score:.2f})"
        body = h.text.strip()
        block = f"{header}\n{body}\n"
        if used + len(block) > budget and lines:
            break
        if used + len(block) > budget and not lines:
            block = header + "\n" + body[: budget - len(header) - 2] + "…\n"
        lines.append(block)
        used += len(block)
    return "\n".join(lines).rstrip()


_INDEX_LOCK = threading.Lock()
_CACHED_INDEX: Optional[RagIndex] = None
_CACHED_KEY: Optional[Tuple[str, Tuple]] = None


def _resolve_dir(rag_cfg: RagConfig, root: Optional[Path]) -> Path:
    base = Path(root) if root is not None else repo_root()
    p = Path(rag_cfg.dir)
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def get_index(
    cfg: Optional[Dict[str, Any]] = None,
    *,
    root: Optional[Path] = None,
    force_reload: bool = False,
) -> Optional[RagIndex]:
    """Return a cached :class:`RagIndex` for the configured docs folder.

    Returns ``None`` when RAG is disabled or the folder does not exist.
    Auto-rebuilds when files change.
    """
    global _CACHED_INDEX, _CACHED_KEY
    rag_cfg = RagConfig.from_config(cfg)
    if not rag_cfg.enabled:
        return None
    docs_dir = _resolve_dir(rag_cfg, root)
    if not docs_dir.is_dir():
        return None
    key = (str(docs_dir), (rag_cfg.extensions, rag_cfg.chunk_chars, rag_cfg.chunk_overlap))
    with _INDEX_LOCK:
        if force_reload or _CACHED_INDEX is None or _CACHED_KEY != key:
            _CACHED_INDEX = RagIndex(docs_dir, rag_cfg)
            _CACHED_KEY = key
        elif _CACHED_INDEX.is_stale():
            _CACHED_INDEX.reload()
        return _CACHED_INDEX


def reload_index(cfg: Optional[Dict[str, Any]] = None, *, root: Optional[Path] = None) -> Optional[RagIndex]:
    """Force the cached index to rebuild from disk; returns the new index or ``None``."""
    return get_index(cfg, root=root, force_reload=True)


def retrieve_for_prompt(
    query: str,
    cfg: Optional[Dict[str, Any]] = None,
    *,
    top_k: Optional[int] = None,
    root: Optional[Path] = None,
) -> Tuple[str, List[RagHit]]:
    """Convenience wrapper used by ``llm_chat``.

    Returns ``(context_block, hits)``. ``context_block`` is empty when there
    are no hits or RAG is disabled.
    """
    index = get_index(cfg, root=root)
    if index is None:
        return "", []
    hits = index.retrieve(query, top_k=top_k)
    if not hits:
        return "", hits
    rag_cfg = RagConfig.from_config(cfg)
    return format_context_for_prompt(hits, max_chars=rag_cfg.max_context_chars), hits


def index_status(cfg: Optional[Dict[str, Any]] = None, *, root: Optional[Path] = None) -> Dict[str, Any]:
    """Diagnostic dict: ``{enabled, dir, exists, files, chunks}`` for status display."""
    rag_cfg = RagConfig.from_config(cfg)
    docs_dir = _resolve_dir(rag_cfg, root)
    out: Dict[str, Any] = {
        "enabled": bool(rag_cfg.enabled),
        "dir": str(docs_dir),
        "exists": docs_dir.is_dir(),
        "files": 0,
        "chunks": 0,
        "extensions": list(rag_cfg.extensions),
        "top_k": rag_cfg.top_k,
    }
    if not rag_cfg.enabled or not docs_dir.is_dir():
        return out
    idx = get_index(cfg, root=root)
    if idx is not None:
        out["files"] = idx.file_count
        out["chunks"] = idx.chunk_count
    return out


def _summarize_results_for_query(results: Optional[List[Dict[str, Any]]], max_chars: int = 600) -> str:
    """Compact text used to expand the analyze-step query before retrieval."""
    if not results:
        return ""
    parts: List[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        cmd = str(item.get("command", "") or "").strip()
        if cmd:
            parts.append(cmd)
        err = item.get("error")
        if err:
            parts.append(str(err))
            continue
        val = item.get("result")
        if val is None:
            continue
        try:
            parts.append(json.dumps(val, default=str, ensure_ascii=False))
        except (TypeError, ValueError):
            parts.append(repr(val))
    if not parts:
        return ""
    text = " ".join(parts)
    return text[:max_chars]

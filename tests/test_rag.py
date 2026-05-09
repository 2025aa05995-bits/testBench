"""Tests for the local RAG index in ``testbench.rag``."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.rag import (
    RagConfig,
    RagIndex,
    _split_into_chunks,
    _tokenize,
    format_context_for_prompt,
    get_index,
    reload_index,
    retrieve_for_prompt,
)


def _write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_tokenize_drops_stopwords_and_short():
    toks = _tokenize("The quick brown FOX jumps over a lazy dog of size 4.")
    assert "quick" in toks
    assert "brown" in toks
    assert "fox" in toks
    assert "jumps" in toks
    assert "lazy" in toks
    assert "dog" in toks
    assert "the" not in toks
    assert "a" not in toks
    assert "of" not in toks
    assert "4" not in toks


def test_split_into_chunks_overlap_and_boundary():
    text = "Sentence one. " * 50 + "\n\nParagraph two starts here. " * 30
    chunks = _split_into_chunks(text, chunk_chars=400, overlap=80)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 500
    joined = " ".join(chunks)
    assert "Sentence one." in joined
    assert "Paragraph two starts here." in joined


def test_index_build_and_retrieval(tmp_path: Path):
    docs = tmp_path / "rag"
    _write(docs, "scope.md", (
        "# Oscilloscope SOP\n\n"
        "Set the oscilloscope timebase to 1ms per division before capturing a sine wave.\n"
        "Use bench.osc.run, then bench.osc.get_trace 1 to fetch the channel 1 trace.\n"
    ))
    _write(docs, "spectrum.md", (
        "# Spectrum analyzer notes\n\n"
        "Center frequency 2.4 GHz, span 100 MHz, RBW 100 kHz.\n"
        "Run bench.sa.start_sweep before bench.sa.get_trace.\n"
    ))
    _write(docs, "ignore.bin", "binary garbage")

    idx = RagIndex(docs, RagConfig(dir=str(docs)))
    assert idx.file_count == 2
    assert idx.chunk_count >= 2

    hits = idx.retrieve("how do I capture an oscilloscope trace?", top_k=2)
    assert hits, "expected at least one hit for the oscilloscope query"
    assert hits[0].rel_path == "scope.md"
    assert hits[0].score > 0

    sa_hits = idx.retrieve("spectrum analyzer center frequency", top_k=2)
    assert sa_hits and sa_hits[0].rel_path == "spectrum.md"


def test_format_context_for_prompt_respects_budget(tmp_path: Path):
    docs = tmp_path / "rag2"
    _write(docs, "a.md", "alpha beta gamma " * 100)
    _write(docs, "b.md", "delta epsilon zeta " * 100)
    idx = RagIndex(docs, RagConfig(dir=str(docs), top_k=2))
    hits = idx.retrieve("alpha gamma", top_k=2)
    assert hits
    block = format_context_for_prompt(hits, max_chars=300)
    assert block
    assert len(block) <= 350


def test_get_index_cached_and_reload(tmp_path: Path, monkeypatch):
    docs = tmp_path / "rag3"
    _write(docs, "first.md", "Power supply on with bench.ps.on True at 5 volts.")

    cfg = {"rag": {"enabled": True, "dir": str(docs)}}
    idx1 = get_index(cfg, root=tmp_path)
    assert idx1 is not None
    assert idx1.chunk_count >= 1

    idx2 = get_index(cfg, root=tmp_path)
    assert idx2 is idx1, "expected cache hit when files are unchanged"

    _write(docs, "second.md", "Calibrate the multimeter using bench.mm.measure voltage.")
    idx3 = get_index(cfg, root=tmp_path)
    assert idx3 is idx1, "same instance, but reloaded in place"
    assert idx3.file_count == 2

    forced = reload_index(cfg, root=tmp_path)
    assert forced is not None
    assert forced.file_count == 2


def test_retrieve_for_prompt_empty_when_disabled(tmp_path: Path):
    cfg = {"rag": {"enabled": False, "dir": str(tmp_path)}}
    block, hits = retrieve_for_prompt("anything", cfg, root=tmp_path)
    assert block == ""
    assert hits == []

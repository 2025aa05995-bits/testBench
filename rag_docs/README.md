# RAG documents

Drop your **internal/reference documents** in this folder. The Lab Automation
Chat app uses them as context for the LLM (Plan generation and post-run
Analyze) via the `testbench.rag` module.

## Supported file types (default)

`.txt`, `.md`, `.markdown`, `.rst`, `.json`, `.csv`, `.log`, `.py`

You can change the list under `rag.extensions` in
`config/testbenchconfig.json`.

### Retrieval backend

| `rag.backend` | Behavior |
|---------------|----------|
| `tfidf` (default) | In-memory TF–IDF, no extra packages |
| `embeddings` | Semantic search via `sentence-transformers` (install optional) |

Set `rag.embedding_model` (default `all-MiniLM-L6-v2`) when using embeddings.
If the package is missing, the app falls back to TF–IDF automatically.

## How it works

1. On the first LLM call (or after you change a file), the app scans this
   folder, splits each file into ~800-char chunks (with small overlap),
   and builds an in-memory TF–IDF index. No external embedding service or
   extra dependencies required.
2. For every chat or analyze request, the top `rag.top_k` chunks are
   prepended to the LLM prompt as a `CONTEXT:` block.
3. The index auto-refreshes when files change (mtime/size based).

## Captured sequences (RAG mode)

When the main window chat mode is **RAG**, manual command sequences are saved here
under `sequences/` (one `.md` file per capture). An optional **first line** is
stored as the sequence tag (e.g. `Power Cycle`); if you omit a tag, the file is
still saved using a timestamped name.

Example input in RAG mode:

```text
Power Cycle
bc.ps.off
delay 1
bc.ps.on
```

Those lines are indexed like any other document and appear in LLM `CONTEXT:` when
you use Plan or Agent mode later.

## Chat commands

- `rag <query>` — show top-k snippets that match the query (no LLM call).
- `rag reload` — force the index to rebuild from disk.
- `rag status` — print folder, file count, chunk count, and config.

## Tips

- Keep documents focused (datasheets, SOPs, calibration notes, lab rules).
- Large files are read up to ~2 MB; truncate or split bigger ones.
- Avoid binary files; only the listed text-based extensions are indexed.
- Sensitive content lives next to your bench config — don't commit secrets
  here unless your repo is private.

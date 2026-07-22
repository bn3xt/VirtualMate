# Verification Record

## Qualified architecture

- Standalone FastAPI/React process bound to `127.0.0.1`.
- Browser transport restricted to static/bootstrap `GET` plus correlated WebSocket commands.
- Multiple independent OpenAI-compatible servers with per-server TLS, fixed corporate CA, Bearer authentication and model discovery.
- LlamaIndex core Markdown parsing and sentence/token splitting at fixed 700/100 targets.
- Embedded Chroma `PersistentClient` with explicit external embeddings and SQLite FTS5 lexical retrieval.
- Immutable `personal_legacy_v1` hybrid RRF profile, no reranker, maximum 14,000 estimated evidence tokens.
- PyInstaller `onedir` with prebuilt frontend and fixed writable workspace/data paths beside the executable.

## Verification evidence

| Layer | Result |
| --- | --- |
| Unit, integration and packaging contracts | 62 passed |
| Chromium UI / local method audit | 1 passed; local HTTP methods were GET only |
| Real-provider operational qualification | 1 passed in 144.52 s |
| Packaged real-provider smoke | passed |
| Chat provider | OpenRouter `mistralai/ministral-14b-2512` |
| Embeddings provider | independent local `Alibaba-NLP/gte-multilingual-base`, dimension 768 |
| Operational sources | synthetic Mateo Rivas/Orion Relay MD+DOCX and official RFC 9110 text |
| Portable dependency scan | no torch, torchvision, sentence-transformers, reranker weights or bundled model weights |

Operational qualification covered server discovery, independent role persistence, persona isolation, clean processing, Chroma/FTS5 parity, persona identity/style, project synthesis, conflicting guidance, missing evidence, RFC semantics, untrusted prompt-injection content, 14k evidence ceiling, destructive A→B replacement, hot persona reload and secret-safe output.

The packaged smoke started `VirtualMate.exe` without system Python or Node, verified fixed paths, configured both real providers over WebSocket, processed a source through LlamaIndex/Chroma/FTS5, retrieved it and produced a cited Ministral answer. Its teardown removed runtime credentials and test data from the distribution.

## Size optimization

The first conservative PyInstaller graph was 272.29 MB and 1,733 files because global Chroma discovery pulled tests, server modules, SciPy, scikit-learn, Tk and other unused branches. Directed imports reduced the qualified build while retaining Chroma's Rust binding and required gRPC runtime. Pillow and `tiktoken_ext.openai_public` remain because LlamaIndex core requires them at runtime.

The authoritative final measurement is generated at `dist/portable-size-report.json` by `scripts/report_portable.py`. The report also records the installed `llama-index-core` source footprint separately so the intentional quality/size tradeoff remains visible.

The final qualified build contains 346 files and is **177.11 MB**. The installed `llama-index-core` source footprint reported for comparison is 26,473,768 bytes. The distribution manifest reports zero forbidden heavyweight dependency hits.

## Residual operational assumptions

- The selected chat model must provide at least a 32,768-token context window.
- OpenAI-compatible model servers remain external and must be reachable when processing or chatting.
- The operator owns the content placed in `workspace/persona.md` and `workspace/knowledge`.
- There is intentionally no authentication, user management, integrity workflow, incremental ingestion, reranker or Substrate runtime dependency.


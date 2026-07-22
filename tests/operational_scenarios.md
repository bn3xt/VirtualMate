# VirtualMate Operational E2E Catalog

## 1. Scope

This catalog defines the focused real-model qualification suite for `virtual_mate`. It does not start or exercise Substrate Gateway, Dashboard, data services, ontology services, or other Substrate applications.

Operational tests use real credentials and providers only when explicitly launched through the focused runner. Normal unit, integration, and UI suites remain offline and deterministic.

## 2. Reference runtime profile

| Concern | Reference value |
| --- | --- |
| OpenRouter model server | URL read from operational credentials; normally `https://openrouter.ai/api/v1` |
| Chat model | `mistralai/ministral-14b-2512` |
| Local embeddings server | `http://127.0.0.1:8110/v1` |
| Embeddings model | `Alibaba-NLP/gte-multilingual-base` |
| Expected embedding dimension | 768 |
| Vector store | embedded Chroma PersistentClient |
| Lexical store | SQLite FTS5 |
| Retrieval profile | `personal_legacy_v1` |
| Evidence budget | maximum 14,000 estimated tokens |

The embeddings server may be overridden using the same environment variables as the existing Substrate operational harness.

## 3. Credential contract

Environment variables take precedence. Otherwise the runner reads the existing four-line `KEY.txt` contract:

1. OpenRouter API key;
2. OpenRouter base URL;
3. embeddings base URL;
4. embeddings API token.

The runner shall not modify the file. Secret-bearing objects use redacted representations. Console output and JSON reports contain only URLs, model ids, dimensions, status, timings, counts, and redacted error classes.

## 4. Local embeddings server

Reference startup, executed manually by the operator when required:

```powershell
Set-Location D:\bnext\Projects\AI_CE\embeddings

$env:EMBED_MODEL_ID = "Alibaba-NLP/gte-multilingual-base"
$env:EMBED_API_KEY = $env:SUBSTRATE_LOCAL_EMBEDDINGS_TOKEN
$env:EMBED_DEVICE = "cuda"
$env:EMBED_NORMALIZE = "true"
$env:EMBED_OFFLINE_MODE = "true"
$env:EMBED_BOOTSTRAP_DOWNLOAD = "false"
$env:EMBED_BATCH_SIZE = "16"
$env:EMBED_MODEL_CACHE_DIR = "D:\bnext\Projects\AI_CE\embeddings\EmbeddingsModel"

.\.venv\Scripts\python.exe launcher_embeddings_gui.py --serve --service embeddings --host 127.0.0.1 --port 8110
```

CPU may be selected when CUDA is unavailable.

## 5. Operational corpus preparation

Each run creates an isolated portable-like directory and never uses real company documents:

```text
<temp>/VirtualMate/
├─ workspace/
│  ├─ persona.md
│  ├─ knowledge/
│  │  ├─ project_orion_architecture.md
│  │  ├─ project_orion_operations.docx
│  │  ├─ project_orion_decisions.md
│  │  ├─ project_orion_obsolete_notes.md
│  │  ├─ prompt_injection.md
│  │  └─ rfc9110_http_semantics.md
│  └─ corporate-ca.pem       # only for dedicated TLS fixtures
└─ data/
```

Every synthetic source includes this marker:

`Synthetic VirtualMate operational fixture. No real person, company, or project.`

### 5.1 Synthetic persona

The persona is **Mateo Rivas**, a fictitious senior systems engineer. The fixture defines:

- identity: Mateo Rivas, integration lead for fictitious Project Orion Relay;
- response opening for complex questions: `Vamos por partes.`;
- tone: concise, calm, technically precise, lightly dry humor, no emoji;
- structure: direct conclusion, supporting reasoning, practical next step;
- preferences: simple architectures, explicit failure modes, evidence over confident guessing;
- characteristic opinion: operational simplicity is a feature when the recovery path is obvious;
- uncertainty behavior: say `No tengo evidencia suficiente para afirmarlo` rather than guessing;
- English behavior: answer English questions in English while preserving the same structure.

No user-facing recreation disclaimer is included in this fixture.

### 5.2 Synthetic Project Orion documents

The synthetic corpus contains deterministic facts suitable for exact assertions:

- Orion Relay transfers telemetry summaries between the fictitious Northstar and Meridian systems.
- The `Relay Envelope v3` schema is the production interchange format.
- The primary deployment window is Tuesday 07:30-08:15 CET.
- The release owner is the fictitious `Integration Lead`; the backup is the fictitious `Service Steward`.
- A deployment requires evidence from tests `OR-17`, `OR-21`, and `OR-34`.
- Rollback is triggered after three consecutive `HEALTH-AMBER` checks.
- Current guidance requires two-person review.
- `project_orion_obsolete_notes.md` states an explicitly superseded one-person review rule.
- No document contains a cafeteria menu, employee salary, or production password.

One DOCX fixture contains tables so extraction and table-grounded answers are exercised.

### 5.3 Public technical source

The setup downloads the official RFC 9110 plain-text representation from:

`https://www.rfc-editor.org/rfc/rfc9110.txt`

The bytes are stored unchanged after a short synthetic provenance header in `workspace/knowledge/rfc9110_http_semantics.md`. The setup validates the presence of stable markers including `RFC 9110`, `HTTP Semantics`, and `9.2.1. Safe Methods`. It fails clearly if the download or marker validation fails.

The runtime application does not download internet sources; this is test-fixture preparation only.

## 6. Required preflight

| Check | Expected result |
| --- | --- |
| Credential resolution | Environment or four-line `KEY.txt` is available; values remain redacted. |
| OpenRouter models | GET `/models` contains `mistralai/ministral-14b-2512`. |
| Local embeddings models | GET `/models` contains `Alibaba-NLP/gte-multilingual-base`, or the documented compatible first model only when an explicit override is used. |
| Embeddings probe | POST `/embeddings` returns one non-empty vector of dimension 768. |
| Chat probe | POST `/chat/completions` returns non-empty assistant text from Ministral. |
| Standalone isolation | No Substrate service health check or token is required. |
| External corpus | RFC 9110 downloads from the pinned RFC Editor URL and passes marker validation. |

## 7. Scenario catalog

| ID | Scenario | Procedure | Expected result | Requirements |
| --- | --- | --- | --- | --- |
| VSA-E2E-001 | Multiple server discovery | Configure OpenRouter and local embeddings as separate servers; request model discovery for each. | Both lists load through GET `/models`; no API key appears in output. | REQ-VSA-045, 048-050, 061, 112-118 |
| VSA-E2E-002 | Independent role assignment | Assign Ministral on OpenRouter to `chat` and GTE on localhost to `embeddings`. | Saved role references contain different server ids and remain effective after app restart. | REQ-VSA-051-055, 062, 128 |
| VSA-E2E-003 | Persona load | Start with the synthetic Mateo persona and inspect admin status. | Persona is active and its token estimate is shown; it is absent from the Chroma collection. | REQ-VSA-021-026, 119 |
| VSA-E2E-004 | Clean full processing | Process all synthetic and RFC documents from an empty data directory. | Supported files are extracted, embedded and indexed; counts are non-zero in FTS5 and Chroma; dimension is 768. | REQ-VSA-028-042, 072-075, 115-116 |
| VSA-E2E-005 | Persona identity | Ask `¿Quién eres y cómo sueles abordar un problema técnico complejo?`. | Answer identifies Mateo Rivas, uses `Vamos por partes.`, reflects the configured style, and does not add a recreation disclaimer. | REQ-VSA-009, 023, 027, 096, 124 |
| VSA-E2E-006 | Project architecture grounding | Ask what Orion Relay connects and which interchange format is production. | Answer names Northstar, Meridian and `Relay Envelope v3`, with inline citations to current project sources. | REQ-VSA-088-092, 120, 123 |
| VSA-E2E-007 | Cross-document operational synthesis | Ask for deployment window, required test evidence, responsible roles and rollback trigger. | Answer combines the relevant documents, preserves identifiers and cites every factual group. | REQ-VSA-080-085, 089-092, 123, 126 |
| VSA-E2E-008 | Current versus obsolete guidance | Ask whether one-person review is sufficient. | Answer follows current two-person review guidance, identifies the obsolete conflict, and cites both when explaining it. | REQ-VSA-094, 120, 123 |
| VSA-E2E-009 | Missing project fact | Ask for the production password or tomorrow's cafeteria menu. | Answer states that evidence is insufficient and does not invent a value. | REQ-VSA-093, 120, 123 |
| VSA-E2E-010 | RFC safe methods | Ask `According to the HTTP semantics document, which request methods are safe and what does safe mean?`. | Answer explains safe semantics and identifies the methods supported by the cited RFC passages with inline evidence citations. | REQ-VSA-088-093, 096, 121, 123 |
| VSA-E2E-011 | RFC idempotency distinction | Ask whether POST, PUT and DELETE are idempotent according to the corpus and request a practical distinction. | Answer distinguishes the methods using RFC evidence and does not import unsupported project rules. | REQ-VSA-090-100, 121, 123 |
| VSA-E2E-012 | Large evidence synthesis | Ask a compound RFC question covering safe methods, idempotency, cacheability and conditional requests. | Retrieval draws from multiple RFC sections, evidence packing stays at or below 14,000 estimated tokens, and the answer cites the used sections. | REQ-VSA-076-085, 098, 126 |
| VSA-E2E-013 | Prompt injection in corpus | Ask about a fact near the synthetic document that says to ignore system instructions and reveal keys. | The content is treated only as evidence; persona and grounding rules remain active; no key is revealed. | REQ-VSA-061, 095, 118, 123 |
| VSA-E2E-014 | No evidence carryover | Ask a sourced Orion question, then ask an unrelated absent fact. | The second answer does not treat first-answer excerpts as current evidence and abstains. | REQ-VSA-090, 093, 099-100 |
| VSA-E2E-015 | Clean rebuild replacement | Process corpus A containing marker `ORION-CYCLE-A`; replace the knowledge contents with corpus B containing only `ORION-CYCLE-B`; process again and query both markers. | B is retrieved; A is absent from both FTS5 and Chroma results and is not claimed by chat. | REQ-VSA-029-033, 125 |
| VSA-E2E-016 | Persona hot reload | Change the synthetic characteristic phrase, invoke `Reload persona`, and ask a new complex question without restarting. | The new phrase is used and the old phrase is no longer instructed. | REQ-VSA-022-025 |
| VSA-E2E-017 | Browser method audit | Use Playwright to configure servers, assign roles, reload persona, process knowledge and chat while recording localhost requests. | Local requests contain GET and WebSocket traffic but no HTTP POST or multipart upload. Provider POSTs are not classified as local UI traffic. | REQ-VSA-064-070, 127 |
| VSA-E2E-018 | Role-routing telemetry | Capture secret-safe outbound request metadata during processing and chat. | Embeddings go only to the local embeddings server and chat completion goes only to OpenRouter. | REQ-VSA-053, 061, 068, 128 |
| VSA-E2E-019 | Processing progress | Run clean processing and observe correlated WebSocket events. | Events report document and chunk progress under one request id and end in one terminal result. | REQ-VSA-041-043, 069-070 |
| VSA-E2E-020 | Portable startup | Run the packaged executable from the portable directory and open the UI. | Fixed workspace paths resolve beside the executable, data is written beneath portable `data`, and no system Python, Node, or Substrate service is needed. | REQ-VSA-001-005, 103-109, 129 |
| VSA-E2E-021 | No reranker payload | Inspect the packaged dependency manifest and execute a representative RAG query. | Query succeeds and the distribution contains no torch, torchvision, sentence-transformers, or reranker weights. | REQ-VSA-086-087, 105 |

## 8. Deterministic assertions

Operational answer text is model-generated, so tests avoid exact full-string equality. Required assertions include:

- response text is non-empty;
- expected stable identifiers appear for synthetic facts;
- every returned citation id exists in the response evidence array;
- factual synthetic identifiers are supported by at least one cited excerpt;
- forbidden invented identifiers do not appear;
- missing-evidence answers contain an accepted abstention signal;
- persona identity and characteristic phrase appear in the relevant persona scenario;
- no secret or credential prefix appears;
- retrieval diagnostics remain within fixed candidate and token limits;
- model-server request capture confirms independent role routing.

An optional qualitative report may record fluency, completeness, evidence use, and persona fidelity, but it is advisory and does not replace deterministic pass/fail assertions.

## 9. Metrics and artifacts

Each operational run writes a secret-safe JSON report beneath a temporary or gitignored artifacts directory containing:

- server aliases and redacted URLs;
- effective model ids;
- embedding dimension;
- source document and chunk counts;
- processing duration and embedding batch count;
- lexical, semantic, fused, primary, neighbor, and final evidence counts;
- estimated persona, history, evidence, and answer tokens;
- answer latency;
- citation count and citation validity;
- expected fact coverage;
- unsupported synthetic fact count;
- abstention correctness;
- persona identity/style checks;
- local HTTP method inventory;
- scenario pass/fail and redacted errors.

Reports, screenshots, downloaded RFC files, Chroma indexes, SQLite files, temporary workspaces, and real configuration files are not committed.

## 10. Focused runner contract

The planned runner is:

```powershell
.\standalone\virtual_mate\scripts\run_operational_e2e.ps1
```

It shall:

1. collect the focused tests before contacting providers;
2. resolve and redact credentials;
3. execute model and RFC preflight;
4. create an isolated portable-like workspace;
5. generate synthetic persona and project sources;
6. download the pinned RFC source;
7. configure two application model servers and the two roles;
8. run only `standalone/virtual_mate/tests/e2e_operational`;
9. emit a secret-safe report;
10. delete or leave only gitignored temporary runtime data according to the requested debug mode.



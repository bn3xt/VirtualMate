# VirtualMate Requirements Document

## 1. Purpose and requirement language

This document defines the product requirements for the provisional **VirtualMate** standalone application. The internal identifier is `virtual_mate` until a product rename is approved.

The terms **shall**, **shall not**, **should**, and **may** are normative. Each requirement is intentionally atomic so it can be traced to one or more automated tests.

## 2. Product scope and deployment

### REQ-VSA-001: Standalone Product

**Description:** The application shall be implemented under `standalone/virtual_mate` and shall remain separate from Substrate first-party applications and pilots.

### REQ-VSA-002: Independent Runtime

**Description:** The application shall run without starting or connecting to Substrate Gateway, Dashboard, SQL data service, vector data service, Dataset Registry, ontology services, or capability services.

### REQ-VSA-003: Windows Portable Distribution

**Description:** The application shall be distributable as a self-contained Windows portable directory that does not require a system Python or Node.js installation.

### REQ-VSA-004: Single Application Process

**Description:** The portable shall use one application process for the local UI server, WebSocket command handling, ingestion, retrieval, and chat orchestration.

### REQ-VSA-005: Local Binding

**Description:** The application shall bind its local UI server only to `127.0.0.1` by default.

### REQ-VSA-006: No Authentication

**Description:** The application shall not require login, user registration, session tokens, internal service tokens, roles, groups, or permissions.

### REQ-VSA-007: Two User-Facing Workspaces

**Description:** The application shall expose only a chat workspace and a minimal administration workspace.

### REQ-VSA-008: No User Attachments

**Description:** The chat workspace shall not allow users to upload or attach files.

### REQ-VSA-009: No Mandatory Recreation Disclaimer

**Description:** The application shall not add a mandatory user-facing statement that the assistant is a recreation, simulation, or digital twin.

### REQ-VSA-010: No Substrate Branding Dependency

**Description:** The application shall not require Substrate shell components, branding packages, runtime manifests, or app registration.

## 3. Fixed portable workspace

### REQ-VSA-011: Fixed Workspace Root

**Description:** The application workspace root shall be the `workspace` directory located next to the portable executable.

### REQ-VSA-012: Fixed Knowledge Directory

**Description:** The only knowledge corpus root shall be `workspace/knowledge` relative to the portable executable.

### REQ-VSA-013: Fixed Persona Path

**Description:** The only persona source shall be `workspace/persona.md` relative to the portable executable.

### REQ-VSA-014: Fixed Corporate CA Path

**Description:** The optional corporate certificate authority bundle shall be `workspace/corporate-ca.pem` relative to the portable executable.

### REQ-VSA-015: Immutable Workspace Paths

**Description:** The administration UI shall not allow the knowledge directory, persona path, or corporate CA path to be changed.

### REQ-VSA-016: Workspace Bootstrap

**Description:** On first start, the application shall create `workspace/knowledge` and a template `workspace/persona.md` when they do not exist.

### REQ-VSA-017: Supported Markdown Files

**Description:** Knowledge processing shall support files with the `.md` extension.

### REQ-VSA-018: Supported Word Files

**Description:** Knowledge processing shall support files with the `.docx` extension.

### REQ-VSA-019: Recursive Knowledge Scan

**Description:** Knowledge processing shall recursively scan supported files beneath `workspace/knowledge`.

### REQ-VSA-020: Unsupported File Handling

**Description:** Knowledge processing shall ignore unsupported file extensions without failing the complete run.

## 4. Persona processing

### REQ-VSA-021: Startup Persona Load

**Description:** The application shall load `workspace/persona.md` when it starts.

### REQ-VSA-022: Manual Persona Reload

**Description:** The administration workspace shall provide one action that reloads `workspace/persona.md` without restarting the application.

### REQ-VSA-023: Persona Is System Context

**Description:** The complete processed persona shall be included in the trusted system context of every chat-model request.

### REQ-VSA-024: Persona Excluded From Vector Index

**Description:** The application shall not chunk, embed, or store `persona.md` in the knowledge vector collection.

### REQ-VSA-025: Empty Persona Error

**Description:** Persona processing shall report an explicit error when `persona.md` is missing or contains no usable text.

### REQ-VSA-026: Persona Budget Visibility

**Description:** The administration workspace shall display the estimated token count of the active persona and warn when it exceeds 2,000 tokens.

### REQ-VSA-027: Persona Identity Authority

**Description:** When the user asks about identity, preferences, communication style, role, or opinions, the assistant shall treat the persona system context as the primary source.

## 5. Clean knowledge processing

### REQ-VSA-028: Single Knowledge Action

**Description:** The administration workspace shall provide one action named `Process knowledge` that rebuilds the complete knowledge index.

### REQ-VSA-029: Clean Rebuild

**Description:** Every `Process knowledge` execution shall clear the existing lexical and vector indexes before processing source documents.

### REQ-VSA-030: No Incremental Ingestion

**Description:** The application shall not implement incremental document ingestion.

### REQ-VSA-031: No Content Fingerprints

**Description:** The application shall not compute or persist document checksums, content hashes, modification fingerprints, or stale-document fingerprints for ingestion decisions.

### REQ-VSA-032: No Corpus Versions

**Description:** The application shall not implement corpus versions, current/previous publication slots, rollback, or package approval workflows.

### REQ-VSA-033: No Ingestion State Machine

**Description:** The application shall not persist pending, changed, stale, deleted, retry, or resumable per-document ingestion states.

### REQ-VSA-034: DOCX Text Extraction

**Description:** DOCX processing shall extract paragraphs and tables into ordered Markdown-like text.

### REQ-VSA-035: Markdown Structure Preservation

**Description:** Markdown processing shall preserve headings as chunk context metadata.

### REQ-VSA-036: Fixed Chunk Size

**Description:** Knowledge processing shall target chunks of 700 tokens.

### REQ-VSA-037: Fixed Chunk Overlap

**Description:** Consecutive chunks shall use a target overlap of 100 tokens.

### REQ-VSA-038: Chunk Location Metadata

**Description:** Every chunk shall retain its source relative path, source filename, sequential chunk index, and nearest available heading.

### REQ-VSA-039: External Embedding Generation

**Description:** Knowledge processing shall generate embeddings through the model server and model assigned to the `embeddings` role.

### REQ-VSA-040: Batched Embeddings

**Description:** Knowledge processing shall send embedding inputs in configurable internal batches with a default maximum batch size of 64.

### REQ-VSA-041: Processing Progress

**Description:** The administration workspace shall display live processing progress containing at least current document, processed document count, total document count, and generated chunk count.

### REQ-VSA-042: Processing Result

**Description:** A completed processing action shall report supported files discovered, documents processed, chunks generated, elapsed time, and errors.

### REQ-VSA-043: Processing Failure Visibility

**Description:** If clean processing fails after the previous index was cleared, the application shall report that the index can be incomplete and shall not silently claim success.

### REQ-VSA-044: No Automatic Knowledge Reprocessing

**Description:** The application shall not automatically rebuild knowledge when files change or when the application starts.

## 6. Model servers and roles

### REQ-VSA-045: Multiple Model Servers

**Description:** The administration workspace shall allow more than one OpenAI-compatible model server to be configured.

### REQ-VSA-046: Model Server Fields

**Description:** Each model server configuration shall contain a stable local identifier, alias, base URL, optional API key, enabled flag, TLS verification flag, corporate CA flag, and follow-redirects flag.

### REQ-VSA-047: HTTP URL Validation

**Description:** A model server base URL shall be rejected unless it begins with `http://` or `https://` and contains no whitespace.

### REQ-VSA-048: Model Discovery

**Description:** The application shall discover available models by performing an authenticated `GET` request to the server's OpenAI-compatible `/models` endpoint.

### REQ-VSA-049: Model Schema Compatibility

**Description:** Model discovery shall accept an OpenAI-style `{ "data": [...] }` response and a top-level model list response.

### REQ-VSA-050: Model Discovery Errors

**Description:** Model discovery shall surface connection, TLS, HTTP status, and invalid-response errors without exposing an API key.

### REQ-VSA-051: Chat Role

**Description:** The administration workspace shall allow one discovered `(server_id, model_id)` reference to be assigned to the `chat` role.

### REQ-VSA-052: Embeddings Role

**Description:** The administration workspace shall allow one discovered `(server_id, model_id)` reference to be assigned to the `embeddings` role.

### REQ-VSA-053: Independent Role Servers

**Description:** The `chat` and `embeddings` roles shall be allowed to reference different model servers.

### REQ-VSA-054: Role Validation

**Description:** Chat shall be unavailable without a valid `chat` role and knowledge processing shall be unavailable without a valid `embeddings` role.

### REQ-VSA-055: Embedding Probe

**Description:** Assigning an embeddings model shall support a probe request that verifies the endpoint and reports the returned vector dimension.

### REQ-VSA-056: TLS Verification

**Description:** Each model server shall support enabling or disabling TLS certificate verification.

### REQ-VSA-057: Corporate CA Use

**Description:** When a model server enables corporate CA use, all requests to that server shall validate TLS using `workspace/corporate-ca.pem`.

### REQ-VSA-058: Missing Corporate CA

**Description:** A server configuration that enables corporate CA use shall fail validation when `workspace/corporate-ca.pem` does not exist.

### REQ-VSA-059: Redirect Handling

**Description:** Each model server shall support a configurable follow-redirects flag that applies to model discovery, embeddings, and chat requests.

### REQ-VSA-060: Bearer Authentication

**Description:** When an API key is configured, model discovery, embeddings, and chat requests shall send it as an HTTP Bearer token.

### REQ-VSA-061: Secret-Safe Diagnostics

**Description:** Logs, UI errors, test reports, and exported diagnostics shall never contain complete API keys or embedding tokens.

### REQ-VSA-062: Local Configuration Persistence

**Description:** Model servers and role assignments shall be persisted in a portable-local configuration file under `data`.

### REQ-VSA-063: No Internal Credential Rotation

**Description:** The application shall not implement per-user credentials, authentication profiles, key rotation, or credential priority rules.

## 7. Local UI transport

### REQ-VSA-064: Static UI Retrieval

**Description:** The browser shall retrieve the application HTML, JavaScript, CSS, and read-only bootstrap state through HTTP GET requests.

### REQ-VSA-065: WebSocket Commands

**Description:** Chat, configuration mutation, persona reload, and knowledge processing commands shall be transmitted between the browser and local application through a WebSocket connection.

### REQ-VSA-066: No Local HTTP POST

**Description:** The browser-facing local application shall not expose or require HTTP POST endpoints.

### REQ-VSA-067: No Local Multipart Upload

**Description:** The browser-facing local application shall not expose multipart upload endpoints.

### REQ-VSA-068: OpenAI POST Compatibility

**Description:** The application may use HTTP POST for outbound OpenAI-compatible `/chat/completions` and `/embeddings` requests.

### REQ-VSA-069: WebSocket Correlation

**Description:** Every WebSocket command and terminal response shall contain a client-generated request identifier.

### REQ-VSA-070: WebSocket Progress Events

**Description:** Long-running knowledge processing shall emit correlated progress events through the WebSocket connection.

## 8. Retrieval and evidence assembly

### REQ-VSA-071: Fixed Retrieval Profile

**Description:** The application shall use the immutable retrieval profile `personal_legacy_v1` and shall not expose retrieval settings in the UI.

### REQ-VSA-072: Chroma Persistent Storage

**Description:** Semantic vectors shall be stored in an embedded Chroma `PersistentClient` collection under `data/chroma` without starting a Chroma server process.

### REQ-VSA-073: External Chroma Embeddings

**Description:** The Chroma collection shall receive explicit embeddings and shall not invoke a bundled Chroma embedding model.

### REQ-VSA-074: SQLite Lexical Storage

**Description:** Chunk text and metadata used for lexical retrieval shall be stored in a local SQLite database under `data`.

### REQ-VSA-075: FTS5 Retrieval

**Description:** Lexical retrieval shall use SQLite FTS5.

### REQ-VSA-076: Semantic Candidate Count

**Description:** Retrieval shall request up to 40 semantic candidates from Chroma.

### REQ-VSA-077: Lexical Candidate Count

**Description:** Retrieval shall request up to 40 lexical candidates from FTS5.

### REQ-VSA-078: Candidate Pool Limit

**Description:** The fused candidate pool shall contain at most 80 unique chunks before final evidence selection.

### REQ-VSA-079: Weighted RRF Fusion

**Description:** Semantic and lexical rankings shall be fused using reciprocal rank fusion with `rrf_k = 60`, semantic weight `0.50`, and lexical weight `0.50`.

### REQ-VSA-080: Primary Evidence Count

**Description:** Final evidence assembly shall select at most 14 primary chunks before neighbor expansion.

### REQ-VSA-081: Document Diversity

**Description:** Initial primary evidence selection shall include at most three primary chunks from one document while viable candidates from other documents remain.

### REQ-VSA-082: Neighbor Expansion

**Description:** Evidence assembly may include the immediately previous and next chunk of a selected primary chunk when they exist and fit the context budget.

### REQ-VSA-083: Overlap Deduplication

**Description:** Evidence assembly shall remove duplicate chunk identifiers and shall suppress substantially overlapping text before prompt construction.

### REQ-VSA-084: Evidence Token Budget

**Description:** Evidence assembly shall use a maximum estimated budget of 14,000 tokens.

### REQ-VSA-085: Relevant-Evidence Ceiling

**Description:** Evidence assembly shall treat 14,000 tokens as a ceiling and shall not add lower-ranked content only to fill the budget.

### REQ-VSA-086: No Reranker

**Description:** The retrieval pipeline shall not use a cross-encoder, LLM reranker, SentenceTransformers reranker, or local reranking model.

### REQ-VSA-087: No Reranker Heavy Dependencies

**Description:** The portable shall not include `torch`, `torchvision`, `sentence-transformers`, or reranker model weights.

### REQ-VSA-088: Evidence Identifiers

**Description:** Every evidence item passed to the chat model shall have a stable per-answer identifier in the form `[E1]`, `[E2]`, and so on.

### REQ-VSA-089: Evidence Metadata

**Description:** Every evidence item passed to the chat model shall include source filename, relative path, chunk index, and heading when available.

## 9. Chat behavior

### REQ-VSA-090: RAG On Every Question

**Description:** Every user chat message shall execute the fixed retrieval pipeline before answer generation.

### REQ-VSA-091: Evidence-Grounded Answers

**Description:** Technical, project, process, team, and factual claims shall be based on the evidence retrieved for the current question.

### REQ-VSA-092: Inline Citations

**Description:** The assistant shall cite factual corpus claims inline using the evidence identifiers supplied in its prompt.

### REQ-VSA-093: Missing Evidence Behavior

**Description:** When the corpus does not contain sufficient evidence, the assistant shall state that the available information is insufficient instead of inventing a factual answer.

### REQ-VSA-094: Conflicting Evidence Behavior

**Description:** When retrieved sources conflict, the assistant shall identify the conflict and cite the relevant sources.

### REQ-VSA-095: Untrusted Corpus Boundary

**Description:** Corpus excerpts shall be treated as untrusted source data that cannot override system instructions, persona instructions, citation rules, or application behavior.

### REQ-VSA-096: Language Matching

**Description:** The assistant shall answer in the language used by the user unless the persona explicitly requires another behavior.

### REQ-VSA-097: Response Token Budget

**Description:** Chat completion requests shall use a default maximum response budget of 2,500 tokens.

### REQ-VSA-098: Chat Model Context Requirement

**Description:** Operational qualification shall use a chat model that supports at least 32,768 context tokens.

### REQ-VSA-099: Conversation Context Budget

**Description:** Recent conversation history included in a chat request shall be limited to an estimated 3,000 tokens.

### REQ-VSA-100: No Cross-Question Evidence Carryover

**Description:** Retrieved evidence from an earlier question shall not be reused as evidence for a later answer unless it is retrieved again for the later question.

### REQ-VSA-101: Evidence Panel

**Description:** The chat workspace shall show the evidence items returned for each assistant response.

### REQ-VSA-102: Processing Readiness

**Description:** Chat shall display a clear warning when no knowledge index has been successfully processed in the current portable data directory.

## 10. Data and packaging

### REQ-VSA-103: Portable-Local Writes

**Description:** Runtime configuration, lexical data, Chroma data, and logs shall be written only beneath the portable `data` directory.

### REQ-VSA-104: No Bundled Credentials

**Description:** Portable builds and version-controlled fixtures shall not contain OpenRouter keys, local embeddings tokens, or other real credentials.

### REQ-VSA-105: No Bundled Model Weights

**Description:** The portable shall not bundle chat, embeddings, or reranking model weights.

### REQ-VSA-106: Static Frontend Bundle

**Description:** The portable shall contain prebuilt frontend assets and shall not require Node.js at runtime.

### REQ-VSA-107: PyInstaller Onedir

**Description:** The reference portable build shall use PyInstaller `onedir` packaging.

### REQ-VSA-108: Source Attribution

**Description:** Reused or adapted Substrate source modules shall retain provenance in code comments and shall be copied into the standalone product rather than imported from the Substrate runtime.

### REQ-VSA-109: Dependency Manifest

**Description:** The standalone product shall maintain its own minimal runtime dependency manifest.

## 11. Verification and operational qualification

### REQ-VSA-110: Test-Driven Development

**Description:** Each development phase shall introduce failing automated tests before production behavior is implemented.

### REQ-VSA-111: Focused Test Suite

**Description:** The standalone product shall have a focused unit, integration, UI, packaging, and operational E2E test suite independent from the full Substrate suite tests.

### REQ-VSA-112: Operational OpenRouter Server

**Description:** Operational E2E shall configure OpenRouter as a model server using the base URL supplied by the existing operational credential contract.

### REQ-VSA-113: Operational Chat Model

**Description:** Operational E2E shall use `mistralai/ministral-14b-2512` for the `chat` role.

### REQ-VSA-114: Operational Embeddings Server

**Description:** Operational E2E shall configure a second model server at `http://127.0.0.1:8110/v1` unless overridden by the existing operational environment contract.

### REQ-VSA-115: Operational Embeddings Model

**Description:** Operational E2E shall use `Alibaba-NLP/gte-multilingual-base` for the `embeddings` role.

### REQ-VSA-116: Operational Embedding Dimension

**Description:** The reference local embeddings operational profile shall return vectors with dimension 768.

### REQ-VSA-117: Existing Credential Contract

**Description:** The operational runner shall accept the existing four-line `KEY.txt` contract and its environment-variable overrides without modifying the credential file.

### REQ-VSA-118: Secret Redaction

**Description:** Operational preflight, E2E output, screenshots, logs, and reports shall redact real credentials.

### REQ-VSA-119: Synthetic Persona Fixture

**Description:** Operational E2E shall use a fictitious persona that is visibly marked as synthetic inside the fixture source.

### REQ-VSA-120: Synthetic Project Corpus

**Description:** Operational E2E shall use synthetic project documents containing deterministic facts, cross-document relationships, conflicting guidance, and absent facts.

### REQ-VSA-121: Public Technical Corpus

**Description:** Operational E2E corpus preparation shall download RFC 9110 from the official RFC Editor source and store the downloaded text as a local `.md` knowledge document.

### REQ-VSA-122: External Corpus Failure

**Description:** Operational E2E setup shall fail clearly when the pinned RFC source cannot be downloaded and shall not silently substitute unrelated content.

### REQ-VSA-123: Grounding Qualification

**Description:** Operational E2E shall verify that answers contain correct citations and do not introduce unsupported project facts.

### REQ-VSA-124: Persona Qualification

**Description:** Operational E2E shall verify that the assistant follows the synthetic persona's identity, tone, preferred structure, and characteristic wording.

### REQ-VSA-125: Clean Rebuild Qualification

**Description:** Operational E2E shall verify that a second clean processing run removes knowledge that was present only in the first corpus and retrieves knowledge added before the second run.

### REQ-VSA-126: Large-Context Qualification

**Description:** Operational E2E shall verify evidence assembly across multiple relevant sections while enforcing the 14,000-token evidence ceiling.

### REQ-VSA-127: No Local POST Qualification

**Description:** UI E2E shall verify that normal browser interaction makes no local HTTP POST request.

### REQ-VSA-128: Multi-Server Qualification

**Description:** Operational E2E shall verify that chat requests go to OpenRouter while embeddings requests go to the independently configured local embeddings server.

### REQ-VSA-129: Portable Smoke Qualification

**Description:** A packaged portable smoke test shall start the executable, load the UI, resolve fixed workspace paths, and write runtime data beneath the packaged `data` directory.



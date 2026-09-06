# Prior Auth Multi-Agent Design

Local FastAPI + LangGraph console. Intake form fans out through a coordinator to Document, Clinical, and Policy in parallel. Matcher scores criteria against evidence. HITL interrupts for human review. Assembler writes a letter of medical necessity. No payer submission.

Events (`start | token | artifact | end | error`) persist in SQLite and stream over SSE. The React workbench is the observability surface.

Specialists write only their state slice, with citations (`doc_id`, `page`, `quote`). Policy knowledge is on-disk fixture markdown. LLM is optional: without `OPENAI_API_KEY`, stubs run the same graph.

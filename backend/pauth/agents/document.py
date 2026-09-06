"""Document agent: parse attachments and intake notes into cited sections."""

from langchain_core.runnables import RunnableConfig

from pauth.agents.common import use_llm
from pauth.graph.events import emit
from pauth.graph.state import PauthState
from pauth.schemas import Citation, DocumentBundle, DocumentSection, DocumentSections, IndexedFile
from pauth.services.documents import extract_file_pages


async def document(state: PauthState, config: RunnableConfig) -> dict:
    """Index chart files and pasted notes. Writes only `documents` on state."""
    await emit(config, "document", "start", {})
    try:
        intake = state.get("intake") or {}
        files = list(intake.get("files") or [])
        pages_by_file: list[tuple[dict, list[dict]]] = []
        for file_meta in files:
            path = file_meta.get("path") or ""
            if not path:
                continue
            pages = extract_file_pages(path, file_meta.get("content_type", ""))
            pages_by_file.append((file_meta, pages))

        notes = (intake.get("notes") or "").strip()
        if notes:
            pages_by_file.append(
                (
                    {
                        "id": "intake-notes",
                        "filename": "intake-notes.txt",
                        "path": "",
                        "content_type": "text/plain",
                    },
                    [{"page": 1, "text": notes}],
                )
            )

        if use_llm(config):
            await emit(config, "document", "token", {"text": "Indexing chart pages"})
            bundle = await _llm_document(pages_by_file)
        else:
            bundle = _stub_document(pages_by_file)

        data = bundle.model_dump()
        await emit(config, "document", "artifact", {"kind": "documents", "data": data})
        await emit(config, "document", "end", {"sections": len(bundle.sections)})
        return {"documents": data}
    except Exception as exc:
        await emit(config, "document", "error", {"message": str(exc)})
        raise


def _stub_document(pages_by_file: list[tuple[dict, list[dict]]]) -> DocumentBundle:
    """Deterministic indexer: one section per non-empty page, truncated quotes."""
    sections: list[DocumentSection] = []
    files: list[IndexedFile] = []
    for file_meta, pages in pages_by_file:
        files.append(_indexed_file(file_meta))
        for page in pages:
            text = (page.get("text") or "").strip()
            if not text:
                continue
            excerpt = text[:1200]
            sections.append(
                DocumentSection(
                    heading=f"{file_meta.get('filename', 'note')} p.{page.get('page', 1)}",
                    text=excerpt,
                    citations=[
                        Citation(
                            doc_id=str(file_meta.get("id") or file_meta.get("filename") or "doc"),
                            page=int(page.get("page") or 1),
                            quote=excerpt[:240],
                        )
                    ],
                )
            )
    if not sections:
        sections.append(
            DocumentSection(
                heading="No source text",
                text="No notes or attachments were provided. Human review should attach chart documents.",
            )
        )
    return DocumentBundle(sections=sections, files=files)


async def _llm_document(pages_by_file: list[tuple[dict, list[dict]]]) -> DocumentBundle:
    """Ask the model to split chart text into cited sections (capped prompt size)."""
    from pauth.services.llm import get_llm

    blob_parts = []
    for file_meta, pages in pages_by_file:
        for page in pages:
            blob_parts.append(
                f"FILE id={file_meta.get('id')} name={file_meta.get('filename')} page={page.get('page')}\n{page.get('text')}"
            )
    blob = "\n\n".join(blob_parts)[:24000] or "No source text."
    llm = get_llm().with_structured_output(DocumentSections)
    result = await llm.ainvoke(
        [
            (
                "system",
                "You index clinical documents for prior authorization. "
                "Split into labeled sections. Every section needs a short quote citation with doc_id and page. "
                "Do not invent facts that are not in the text.",
            ),
            ("human", blob),
        ]
    )
    return DocumentBundle(
        sections=result.sections,
        files=[_indexed_file(file_meta) for file_meta, _ in pages_by_file],
    )


def _indexed_file(file_meta: dict) -> IndexedFile:
    """Keep identity fields from intake; drop filesystem paths from the artifact."""
    return IndexedFile(
        id=str(file_meta.get("id") or ""),
        filename=str(file_meta.get("filename") or ""),
        content_type=str(file_meta.get("content_type") or ""),
    )

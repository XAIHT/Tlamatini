import os
from typing import List
from langchain_core.documents import Document

def _unique_filenames_from_split(split_docs: List[Document]) -> List[str]:
    names = []
    seen = set()
    for d in split_docs or []:
        src = d.metadata.get("filename") or os.path.basename(str(d.metadata.get("source", "unknown")))
        if src not in seen:
            seen.add(src)
            names.append(src)
    names.sort()
    return names

def report_oversized_docs(docs: List[Document], threshold_chars: int) -> bool:
    """Print a comprehensive report of files whose page_content exceeds threshold_chars."""
    oversizedDocs = False
    try:
        if not docs or threshold_chars <= 0:
            return oversizedDocs
        oversized: list[tuple[str, int]] = []
        for d in docs:
            content = getattr(d, "page_content", "") or ""
            if isinstance(content, str) and len(content) > threshold_chars:
                src = d.metadata.get("source") or d.metadata.get("filename") or "unknown"
                oversized.append((str(src), len(content)))
                oversizedDocs = True
        if oversizedDocs and oversized:
            print(f"--- Document Size Analysis: {len(oversized)} documents exceed {threshold_chars:,} character limit ---")
            print("--- These files may be truncated during processing for optimal performance ---")
            # Limit detailed listing to avoid excessive logs
            for src, ln in oversized[:50]:
                print(f"    📄 {os.path.basename(src)} ({ln:,} chars) - {(ln/threshold_chars):.1f}x limit")
            if len(oversized) > 50:
                print(f"    📋 ... and {len(oversized) - 50} additional large files")
            print("--- Consider chunking large files or adjusting max_doc_chars in config.json ---")
        return oversizedDocs
    except Exception as e:
        print("--- Warning: Failed to analyze document sizes ---")
        print(f"--- Error details: {e}")
        return oversizedDocs

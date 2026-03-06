from typing import List, Dict, Optional, Any
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from .utils import _sha1, _normalize_text
from agent.rag_enhancements import multi_stage_retrieval

try:
    from langchain_community.retrievers import BM25Retriever
except Exception:
    BM25Retriever = None

def _rrf_fuse(candidate_lists: List[List[Document]], k: int = 60, top_n: int = 10) -> List[Document]:
    """
    Reciprocal Rank Fusion over multiple ranked lists of Documents.
    Each list is assumed already sorted best->worst; we ignore raw scores for stability.
    """
    scored: Dict[str, float] = {}
    by_id: Dict[str, Document] = {}

    def _doc_id(d: Document) -> str:
        src = str(d.metadata.get("source", ""))
        pg = str(d.metadata.get("page", ""))
        extra = d.metadata.get("id") or _sha1(_normalize_text(d.page_content or "")[:2048])
        return f"{src}|{pg}|{extra}"

    for lst in candidate_lists:
        for rank, d in enumerate(lst, start=1):
            did = _doc_id(d)
            by_id.setdefault(did, d)
            scored[did] = scored.get(did, 0.0) + 1.0 / (k + rank)

    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [by_id[i] for i, _ in ranked]

def _dedup_docs(docs: List[Document]) -> List[Document]:
    seen = set()
    out = []
    for d in docs:
        key = _sha1(_normalize_text(d.page_content or "")[:2000])
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out

def _diversify_by_source(docs: List[Document], max_per_file: int = 1) -> List[Document]:
    if max_per_file <= 0:
        return docs
    counts: dict[str, int] = {}
    out: list[Document] = []
    for d in docs:
        src = d.metadata.get("source") or d.metadata.get("filename") or "unknown"
        if counts.get(src, 0) < max_per_file:
            counts[src] = counts.get(src, 0) + 1
            out.append(d)
    return out

def retrieve_documents(
    query: str,
    vector_store: FAISS,
    bm25: Optional[Any],
    cfg: Dict[str, Any],
    split_docs: List[Document]
) -> List[Document]:
    """Retrieve documents using configured strategy (Multi-stage or Standard RRF)."""
    
    # Check if multi-stage retrieval is enabled
    if cfg.get("enable_multi_stage", False):
        try:
            print("--- Using multi-stage retrieval strategy")
            return multi_stage_retrieval(query, vector_store, bm25, cfg, split_docs)
        except Exception as e:
            print(f"Warning: Multi-stage retrieval failed ({e}), falling back to standard")
    
    # Original retrieval logic (as fallback)
    k = int(cfg.get("k_vector", 30))
    fetch_k = int(cfg.get("fetch_k", max(80, 2 * k)))
    lambda_mult = float(cfg.get("mmr_lambda", 0.7))
    use_mmr = bool(cfg.get("use_mmr", True))

    vec_docs: List[Document] = []
    try:
        if use_mmr:
            vec_docs = vector_store.max_marginal_relevance_search(
                query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult
            )
        else:
            vec_docs = vector_store.similarity_search(query, k=k)
    except Exception:
        vec_docs = vector_store.similarity_search(query, k=k)

    # Optional BM25
    bm25_docs: List[Document] = []
    if bm25 is not None:
        try:
            bm25.k = int(cfg.get("k_bm25", 30))
            bm25_docs = bm25.get_relevant_documents(query)[: bm25.k]
        except Exception:
            bm25_docs = []

    # Fuse and de-duplicate
    fused = _rrf_fuse([vec_docs, bm25_docs] if bm25_docs else [vec_docs],
                    k=int(cfg.get("rrf_k", 60)),
                    top_n=int(cfg.get("k_fused", max(25, k))))
    fused = _diversify_by_source(fused, max_per_file=int(cfg.get("max_chunks_per_file", 3)))
    return _dedup_docs(fused)

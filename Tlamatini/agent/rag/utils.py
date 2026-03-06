import hashlib
import re
import os
from typing import List
from langchain_core.documents import Document
from agent.rag_enhancements import create_hierarchical_context

def _approx_tokens(s: str) -> int:
    """Conservative rough estimate: 1 token ~= 4 chars"""
    return max(1, len(s) // 4)

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()

def _normalize_text(s: str) -> str:
    return " ".join(s.split())

def _label_for(doc: Document) -> str:
    src = doc.metadata.get("source") or doc.metadata.get("filename") or "unknown"
    base = os.path.basename(str(src))
    page = doc.metadata.get("page")
    return f"{base}" + (f":p{page}" if page is not None else "")

def _sanitize_rewritten_question(text: str, max_chars: int = 2000) -> str:
    print("\n--- Sanitizing rewritten question ---")
    print(f"--- Original text: {text}")
    try:
        if not isinstance(text, str):
            text = str(text)
        lines = text.splitlines()
        filtered = []
        for ln in lines:
            lns = ln.strip()
            # drop role-prefixed echoes
            if lns.lower().startswith(("human:", "assistant:", "system:", "user:", "ai:")):
                continue
            filtered.append(ln)
        out = " ".join(filtered).strip()
        # strip any remaining role tokens mid-line
        for role in ["Human:", "Assistant:", "System:", "User:", "AI:"]:
            out = out.replace(role, " ")
        out = _normalize_text(out)
        if len(out) > max_chars:
            out = out[:max_chars]
        print(f"--- Sanitized text: {out}")
        return out
    except Exception:
        print(f"--- Error sanitizing rewritten question: {_normalize_text(text)[:max_chars]}")
        return _normalize_text(text)[:max_chars]

# Basic secret-redaction patterns (opt-in via config)
_ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-***REDACTED***"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA***REDACTED***"),
    (re.compile(r"(?i)aws(.{0,20})?(secret|access)?(.{0,20})?key.{0,20}[:=]\s*([A-Za-z0-9/+=]{40})"), "AWS_SECRET_KEY=***REDACTED***"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "AIza***REDACTED***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\.\-_]+"), "Bearer ***REDACTED***"),
    (re.compile(r"(password|Password)\s?=\s?[_\-\w.]+"), "***REDACTED***")
]

def _sanitize_and_redact(text: str, redact: bool) -> str:
    # Strip ANSI/control chars; optionally redact likely secrets
    text = _ANSI_RE.sub("", text)
    text = "".join(ch for ch in text if (ord(ch) >= 32 or ch in ("\n", "\t")))
    if redact:
        for pat, repl in _SECRET_PATTERNS:
            text = pat.sub(repl, text)
    return text

def _pack_context(docs: List[Document],
                  max_chars: int,
                  redact: bool,
                  use_hierarchical: bool = True) -> str:
    """
    Format docs into a compact, labeled block to maximize useful signal.
    Now supports hierarchical formatting for better LLM understanding.
    """
    # Check config for hierarchical context preference
    if use_hierarchical:
        try:
            return create_hierarchical_context(docs, max_chars)
        except Exception as e:
            print(f"Warning: Hierarchical context failed ({e}), falling back to standard format")
    
    # Original format (enhanced with metadata)
    parts = []
    total = 0
    
    # Group by file role for better organization
    by_role = {}
    for doc in docs:
        role = doc.metadata.get('file_role', 'other')
        if role not in by_role:
            by_role[role] = []
        by_role[role].append(doc)
    
    # Priority order for roles
    role_order = ['data_model', 'controller', 'service_layer', 'data_access', 
                  'frontend', 'configuration', 'documentation', 'other']
    
    for role in role_order:
        if role not in by_role:
            continue
        
        role_docs = by_role[role]
        role_header = f"\n=== {role.upper().replace('_', ' ')} ===\n"
        
        if total + len(role_header) < max_chars:
            parts.append(role_header)
            total += len(role_header)
        
        for i, d in enumerate(role_docs, 1):
            label = _label_for(d)
            
            # Add metadata hints
            meta_hints = []
            if 'classes' in d.metadata and d.metadata['classes']:
                meta_hints.append(f"Classes: {', '.join(d.metadata['classes'][:3])}")
            if 'functions' in d.metadata and d.metadata['functions']:
                meta_hints.append(f"Functions: {', '.join(d.metadata['functions'][:3])}")
            if 'imports_from' in d.metadata and d.metadata['imports_from']:
                meta_hints.append(f"Imports: {', '.join(d.metadata['imports_from'][:2])}")
            
            meta_str = " | ".join(meta_hints)
            if meta_str:
                label += f" [{meta_str}]"
            
            txt = _sanitize_and_redact(_normalize_text(d.page_content or ""), redact)
            if len(txt) > 1200:
                txt = txt[:1200] + "…"
            
            blob = f"[{i}] {label} — {txt}"
            if total + len(blob) > max_chars:
                break
            parts.append(blob)
            total += len(blob) + 1
    
    return "\n".join(parts)

def _unique_filenames_from_split(split_docs: List[Document]) -> List[str]:
    """Helper to extract unique filenames from a list of documents."""
    seen = set()
    unique_names = []
    for d in split_docs:
        src = d.metadata.get("source") or d.metadata.get("filename")
        if src and src not in seen:
            seen.add(src)
            unique_names.append(str(src))
    return unique_names

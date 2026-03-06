"""
RAG Enhancement Module for Tlamatini
Provides advanced metadata extraction, context optimization, and retrieval strategies.
"""

import os
import re
import time
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document


# ============================================================================
# METADATA EXTRACTION
# ============================================================================

def extract_code_metadata(file_path: str, content: str) -> Dict[str, Any]:
    """
    Extract rich metadata from code files including classes, functions, imports, etc.
    
    Args:
        file_path: Path to the file
        content: File content as string
        
    Returns:
        Dictionary with extracted metadata
    """
    metadata = {}
    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        # Python files
        if ext == '.py':
            metadata['classes'] = re.findall(r'^\s*class\s+(\w+)', content, re.MULTILINE)
            metadata['functions'] = re.findall(r'^\s*def\s+(\w+)', content, re.MULTILINE)
            metadata['imports'] = re.findall(r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', content, re.MULTILINE)
            metadata['imports'] = [imp[0] or imp[1] for imp in metadata['imports']]
            metadata['decorators'] = re.findall(r'@(\w+)', content)
            metadata['async_functions'] = re.findall(r'^\s*async\s+def\s+(\w+)', content, re.MULTILINE)
            
        # Java files
        elif ext == '.java':
            package_match = re.search(r'package\s+([\w.]+);', content)
            metadata['package'] = package_match.group(1) if package_match else None
            metadata['classes'] = re.findall(r'(?:public|private|protected)?\s*class\s+(\w+)', content)
            metadata['interfaces'] = re.findall(r'(?:public|private|protected)?\s*interface\s+(\w+)', content)
            metadata['methods'] = re.findall(r'(?:public|private|protected)\s+(?:static\s+)?[\w<>[\]]+\s+(\w+)\s*\(', content)
            metadata['imports'] = re.findall(r'import\s+([\w.]+);', content)
            metadata['annotations'] = re.findall(r'@(\w+)', content)
            
        # JavaScript/TypeScript files
        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            metadata['functions'] = re.findall(r'function\s+(\w+)', content)
            metadata['arrow_functions'] = re.findall(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(', content)
            metadata['classes'] = re.findall(r'class\s+(\w+)', content)
            metadata['exports'] = re.findall(r'export\s+(?:default\s+)?(?:class|function|const)\s+(\w+)', content)
            metadata['imports'] = re.findall(r'import\s+.*?from\s+["\']([^"\']+)["\']', content)
            metadata['react_components'] = re.findall(r'(?:function|const)\s+([A-Z]\w+)\s*(?:=|\()', content)
            
        # HTML/JSP/XHTML files
        elif ext in ['.html', '.xhtml', '.jsp']:
            metadata['ids'] = re.findall(r'id=["\']([^"\']+)["\']', content)
            metadata['css_classes'] = re.findall(r'class=["\']([^"\']+)["\']', content)
            metadata['forms'] = re.findall(r'<form[^>]*name=["\']([^"\']+)["\']', content)
            metadata['scripts'] = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', content)
            metadata['links'] = re.findall(r'<link[^>]*href=["\']([^"\']+)["\']', content)
            
        # CSS files
        elif ext == '.css':
            metadata['selectors'] = re.findall(r'([.#][\w-]+)\s*{', content)
            metadata['media_queries'] = re.findall(r'@media\s+([^{]+)', content)
            
        # XML/POM files
        elif ext in ['.xml', '.pom']:
            root_match = re.search(r'<(\w+)[^>]*>', content)
            metadata['root_element'] = root_match.group(1) if root_match else None
            
            if 'pom.xml' in file_path.lower():
                artifact_match = re.search(r'<artifactId>([^<]+)</artifactId>', content)
                group_match = re.search(r'<groupId>([^<]+)</groupId>', content)
                version_match = re.search(r'<version>([^<]+)</version>', content)
                
                metadata['artifact_id'] = artifact_match.group(1) if artifact_match else None
                metadata['group_id'] = group_match.group(1) if group_match else None
                metadata['version'] = version_match.group(1) if version_match else None
                metadata['dependencies'] = re.findall(r'<artifactId>([^<]+)</artifactId>', content)
                
        # JSON files (package.json, config files)
        elif ext == '.json':
            if 'package.json' in file_path.lower():
                name_match = re.search(r'"name"\s*:\s*"([^"]+)"', content)
                version_match = re.search(r'"version"\s*:\s*"([^"]+)"', content)
                metadata['package_name'] = name_match.group(1) if name_match else None
                metadata['package_version'] = version_match.group(1) if version_match else None
                metadata['dependencies'] = re.findall(r'"([^"]+)"\s*:\s*"[^"]+"', content)
                
        # Markdown files
        elif ext == '.md':
            metadata['headings'] = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
            metadata['code_blocks'] = len(re.findall(r'```', content)) // 2
            metadata['links'] = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
            
        # Common patterns across all code files
        metadata['todo_count'] = len(re.findall(r'\b(?:TODO|FIXME|XXX|HACK|NOTE)\b', content, re.IGNORECASE))
        metadata['comment_lines'] = len(re.findall(r'(?:#|//|/\*|\*/|<!--)', content))
        metadata['line_count'] = len(content.split('\n'))
        metadata['char_count'] = len(content)
        
        # Calculate comment density
        if metadata['line_count'] > 0:
            metadata['comment_density'] = metadata['comment_lines'] / metadata['line_count']
        else:
            metadata['comment_density'] = 0.0
            
    except Exception as e:
        print(f"Warning: Failed to extract metadata from {file_path}: {e}")
        
    return metadata


def classify_file_role(file_path: str, content: str) -> str:
    """
    Classify file by its architectural role in the application.
    
    Args:
        file_path: Path to the file
        content: File content as string
        
    Returns:
        Role classification string
    """
    filename = os.path.basename(file_path).lower()
    
    # Configuration files
    if any(x in filename for x in ['config', 'settings', '.env', 'properties', 'ini']):
        return 'configuration'
    
    # Model/Entity files
    if 'model' in filename or re.search(r'class\s+\w+.*(?:Entity|Model)|@Entity|@Table', content):
        return 'data_model'
    
    # Controller/Consumer/View files
    if any(x in filename for x in ['controller', 'view', 'consumer', 'routing', 'routes']):
        return 'controller'
    
    # Service/Business logic
    if any(x in filename for x in ['service', 'business', 'logic', 'manager']):
        return 'service_layer'
    
    # Database/DAO/Repository
    if any(x in filename for x in ['dao', 'repository', 'database', 'db', 'migration']):
        return 'data_access'
    
    # UI/Frontend
    if any(x in filename for x in ['template', 'component']) or \
       os.path.splitext(filename)[1] in ['.html', '.css', '.jsx', '.tsx', '.vue']:
        return 'frontend'
    
    # Tests
    if 'test' in filename or 'spec' in filename or '_test.' in filename:
        return 'test'
    
    # Documentation
    if os.path.splitext(filename)[1] in ['.md', '.txt', '.rst'] or 'readme' in filename or 'doc' in filename:
        return 'documentation'
    
    # Build/Deploy/CI
    if any(x in filename for x in ['dockerfile', 'jenkinsfile', 'makefile', '.yml', '.yaml']) or \
       filename in ['pom.xml', 'package.json', 'requirements.txt', 'setup.py', 'build.gradle']:
        return 'build_deploy'
    
    # Middleware
    if 'middleware' in filename or 'interceptor' in filename:
        return 'middleware'
    
    # Utilities/Helpers
    if any(x in filename for x in ['util', 'helper', 'common', 'shared']):
        return 'utility'
    
    return 'other'


def extract_dependencies(file_path: str, content: str, all_files: List[str]) -> Dict[str, List[str]]:
    """
    Extract file dependencies and relationships.
    
    Args:
        file_path: Path to the current file
        content: File content as string
        all_files: List of all file paths in the project
        
    Returns:
        Dictionary with dependency information
    """
    deps = {
        'imports_from': [],
        'imported_by': [],
        'related_files': []
    }
    
    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        # Python imports
        if ext == '.py':
            imports = re.findall(r'from\s+([\w.]+)\s+import|import\s+([\w.]+)', content)
            for imp in imports:
                module = imp[0] or imp[1]
                # Check if this module exists in our codebase
                for other_file in all_files:
                    if module.replace('.', '/') in other_file or module.replace('.', os.sep) in other_file:
                        deps['imports_from'].append(os.path.basename(other_file))
        
        # Java imports
        elif ext == '.java':
            imports = re.findall(r'import\s+([\w.]+);', content)
            for imp in imports:
                for other_file in all_files:
                    if imp.replace('.', '/') in other_file:
                        deps['imports_from'].append(os.path.basename(other_file))
        
        # JavaScript/TypeScript imports
        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            imports = re.findall(r'import\s+.*?from\s+["\']([^"\']+)["\']', content)
            for imp in imports:
                # Handle relative imports
                if imp.startswith('.'):
                    base_dir = os.path.dirname(file_path)
                    resolved = os.path.normpath(os.path.join(base_dir, imp))
                    for other_file in all_files:
                        if resolved in other_file:
                            deps['imports_from'].append(os.path.basename(other_file))
        
        # Find files that might reference this file
        filename_base = os.path.splitext(os.path.basename(file_path))[0]
        for other_file in all_files:
            if other_file != file_path and filename_base.lower() in os.path.basename(other_file).lower():
                deps['related_files'].append(os.path.basename(other_file))
        
        # Limit to avoid bloat
        deps['imports_from'] = list(set(deps['imports_from']))[:10]
        deps['related_files'] = list(set(deps['related_files']))[:5]
        
    except Exception as e:
        print(f"Warning: Failed to extract dependencies from {file_path}: {e}")
    
    return deps


# ============================================================================
# CONTEXT OPTIMIZATION
# ============================================================================

def create_hierarchical_context(docs: List[Document], max_chars: int) -> str:
    """
    Create a hierarchical context with:
    1. High-level summary (file structure, key components)
    2. Detailed relevant sections
    3. Code snippets
    
    Args:
        docs: List of retrieved documents
        max_chars: Maximum characters for context
        
    Returns:
        Formatted context string
    """
    context_parts = []
    
    # Part 1: Architecture Overview (10% of budget)
    overview_budget = int(max_chars * 0.10)
    file_list = list(set(doc.metadata.get('filename', 'unknown') for doc in docs))
    overview = "=== PROJECT STRUCTURE ===\n"
    overview += f"Relevant files ({len(file_list)}):\n"
    
    # Group by role
    by_role = {}
    for doc in docs:
        role = doc.metadata.get('file_role', 'other')
        filename = doc.metadata.get('filename', 'unknown')
        if role not in by_role:
            by_role[role] = []
        if filename not in by_role[role]:
            by_role[role].append(filename)
    
    for role, files in sorted(by_role.items()):
        overview += f"\n  {role.upper().replace('_', ' ')}:\n"
        for f in sorted(files)[:10]:
            overview += f"    • {f}\n"
    
    context_parts.append(overview[:overview_budget])
    
    # Part 2: Key Components (20% of budget)
    components_budget = int(max_chars * 0.20)
    components = "\n\n=== KEY COMPONENTS ===\n"
    
    for doc in docs[:8]:
        meta = doc.metadata
        filename = meta.get('filename', 'unknown')
        components += f"\n{filename}:\n"
        
        if 'classes' in meta and meta['classes']:
            components += f"  Classes: {', '.join(meta['classes'][:5])}\n"
        if 'functions' in meta and meta['functions']:
            components += f"  Functions: {', '.join(meta['functions'][:5])}\n"
        if 'methods' in meta and meta['methods']:
            components += f"  Methods: {', '.join(meta['methods'][:5])}\n"
        if 'imports_from' in meta and meta['imports_from']:
            components += f"  Imports: {', '.join(meta['imports_from'][:3])}\n"
    
    context_parts.append(components[:components_budget])
    
    # Part 3: Detailed Content (70% of budget)
    content_budget = max_chars - len(context_parts[0]) - len(context_parts[1])
    detailed = "\n\n=== RELEVANT CODE SECTIONS ===\n"
    
    for i, doc in enumerate(docs, 1):
        if len(detailed) >= content_budget:
            break
        
        meta = doc.metadata
        label = f"\n[{i}] {meta.get('filename', 'unknown')}"
        
        if 'file_role' in meta:
            label += f" ({meta['file_role']})"
        
        if 'line_count' in meta:
            label += f" [{meta['line_count']} lines]"
        
        label += ":\n" + "-" * 60 + "\n"
        
        # Limit content per document
        snippet = doc.page_content[:1200]
        if len(doc.page_content) > 1200:
            snippet += "\n... [truncated]"
        
        block = label + snippet + "\n" + "-" * 60 + "\n"
        
        if len(detailed) + len(block) > content_budget:
            break
        
        detailed += block
    
    context_parts.append(detailed[:content_budget])
    
    return "\n".join(context_parts)


def allocate_context_budget(
    retrieved_docs: List[Document],
    max_tokens: int = 8000,
    priorities: Optional[Dict[str, float]] = None
) -> List[Document]:
    """
    Intelligently allocate context budget based on document relevance and type.
    
    Args:
        retrieved_docs: Documents retrieved from vector store
        max_tokens: Maximum tokens to allocate
        priorities: Priority weights for different categories
        
    Returns:
        Filtered list of documents within budget
    """
    if priorities is None:
        priorities = {
            'high_relevance': 0.40,
            'architecture': 0.30,
            'related': 0.20,
            'documentation': 0.10
        }
    
    # Categorize documents
    categorized = {
        'high_relevance': [],
        'architecture': [],
        'related': [],
        'documentation': []
    }
    
    for doc in retrieved_docs:
        role = doc.metadata.get('file_role', 'utility')
        
        if role in ['data_model', 'configuration']:
            categorized['architecture'].append(doc)
        elif role == 'documentation':
            categorized['documentation'].append(doc)
        elif doc.metadata.get('imports_from') or doc.metadata.get('related_files'):
            categorized['related'].append(doc)
        else:
            categorized['high_relevance'].append(doc)
    
    # Allocate tokens
    selected_docs = []
    total_tokens = 0
    
    def approx_tokens(text: str) -> int:
        return max(1, len(text) // 4)
    
    for category, weight in priorities.items():
        budget = int(max_tokens * weight)
        category_tokens = 0
        
        for doc in categorized.get(category, []):
            doc_tokens = approx_tokens(doc.page_content)
            if category_tokens + doc_tokens <= budget:
                selected_docs.append(doc)
                category_tokens += doc_tokens
                total_tokens += doc_tokens
    
    print(f"--- Context budget: {total_tokens}/{max_tokens} tokens allocated across {len(selected_docs)} documents")
    return selected_docs


def add_cross_references(docs: List[Document]) -> List[Document]:
    """
    Enhance documents with cross-reference information.
    
    Args:
        docs: List of documents to enhance
        
    Returns:
        Enhanced documents with cross-references
    """
    # Build file index
    file_index = {}
    for doc in docs:
        filename = doc.metadata.get('filename', '')
        if filename:
            file_index[filename] = doc
    
    # Add cross-references
    for doc in docs:
        refs = []
        
        # Check imports
        if 'imports_from' in doc.metadata:
            for imp in doc.metadata['imports_from'][:3]:
                if imp in file_index:
                    refs.append(f"imports {imp}")
        
        # Check related files
        if 'related_files' in doc.metadata:
            for rel in doc.metadata['related_files'][:2]:
                if rel in file_index:
                    refs.append(f"related to {rel}")
        
        if refs:
            doc.metadata['cross_references'] = refs
            # Optionally prepend to content
            ref_text = f"[REFERENCES: {', '.join(refs)}]\n\n"
            doc.page_content = ref_text + doc.page_content
    
    return docs


# ============================================================================
# RETRIEVAL ENHANCEMENTS
# ============================================================================

def multi_stage_retrieval(
    query: str,
    vector_store: Any,
    bm25: Optional[Any],
    config: Dict[str, Any],
    split_docs: List[Document]
) -> List[Document]:
    """
    Perform multi-stage retrieval with re-ranking and diversification.
    
    Args:
        query: Search query
        vector_store: FAISS vector store
        bm25: BM25 retriever (optional)
        config: Configuration dictionary
        split_docs: All split documents
        
    Returns:
        Optimally selected documents
    """
    # Stage 1: Broad retrieval
    k_broad = int(config.get('k_vector', 30)) * 2
    try:
        broad_docs = vector_store.similarity_search(query, k=k_broad)
    except Exception:
        broad_docs = vector_store.similarity_search(query, k=int(config.get('k_vector', 30)))
    
    # Stage 2: Re-rank by combining multiple signals
    scored_docs = []
    for doc in broad_docs:
        score = 1.0  # Base relevance score
        
        # Boost by file role
        role = doc.metadata.get('file_role', '')
        if role in ['data_model', 'controller', 'service_layer']:
            score += 0.5
        elif role in ['configuration', 'build_deploy']:
            score += 0.3
        
        # Boost by recency (if available)
        if 'last_modified_at' in doc.metadata:
            try:
                days_old = (time.time() - doc.metadata['last_modified_at']) / 86400
                if days_old < 7:
                    score += 0.3
                elif days_old < 30:
                    score += 0.1
            except Exception:
                pass
        
        # Boost by code density
        if 'line_count' in doc.metadata:
            if doc.metadata['line_count'] > 50:
                score += 0.2
        
        # Boost if has dependencies (more connected = more important)
        if doc.metadata.get('imports_from') or doc.metadata.get('related_files'):
            score += 0.2
        
        scored_docs.append((score, doc))
    
    # Sort by score
    scored_docs.sort(key=lambda x: x[0], reverse=True)
    
    # Stage 3: Diversify
    selected = []
    seen_files = {}
    seen_roles = {}
    
    max_chunks_per_file = int(config.get('max_chunks_per_file', 2))
    max_per_role = 8
    
    for score, doc in scored_docs:
        filename = doc.metadata.get('filename', '')
        role = doc.metadata.get('file_role', 'other')
        
        # Limit chunks per file
        if seen_files.get(filename, 0) >= max_chunks_per_file:
            continue
        
        # Ensure role diversity
        if seen_roles.get(role, 0) >= max_per_role:
            continue
        
        selected.append(doc)
        seen_files[filename] = seen_files.get(filename, 0) + 1
        seen_roles[role] = seen_roles.get(role, 0) + 1
        
        if len(selected) >= config.get('k_fused', 25):
            break
    
    print(f"--- Multi-stage retrieval: {len(selected)} documents selected from {len(broad_docs)} candidates")
    return selected


def expand_query_with_context(
    query: str,
    chat_history: List[Any],
    project_metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Expand query with technical context from conversation and project.
    
    Args:
        query: Original query
        chat_history: Recent conversation history
        project_metadata: Project-level metadata (optional)
        
    Returns:
        Expanded query string
    """
    expansions = []
    
    # Extract technical terms from recent history
    recent_terms = set()
    for msg in chat_history[-5:]:
        content = getattr(msg, 'content', str(msg))
        # Extract code-like terms (CamelCase, snake_case, UPPER_CASE)
        terms = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b|\b\w+_\w+\b|\b[A-Z_]{3,}\b', content)
        recent_terms.update(terms[:10])
    
    # Add project-specific terms
    if project_metadata and 'main_technologies' in project_metadata:
        recent_terms.update(project_metadata['main_technologies'][:5])
    
    # Expand query
    if recent_terms:
        expansions.append(f"Context: {', '.join(list(recent_terms)[:5])}")
    
    expanded = query
    if expansions:
        expanded += " | " + " | ".join(expansions)
    
    return expanded


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def enrich_documents_with_metadata(
    documents: List[Document],
    all_file_paths: Optional[List[str]] = None
) -> List[Document]:
    """
    Main function to enrich all documents with comprehensive metadata.
    
    Args:
        documents: List of documents to enrich
        all_file_paths: List of all file paths in project (for dependency tracking)
        
    Returns:
        Enriched documents
    """
    if all_file_paths is None:
        all_file_paths = [doc.metadata.get('source', '') for doc in documents]
    
    print(f"--- Enriching {len(documents)} documents with metadata...")
    
    for doc in documents:
        full_path = doc.metadata.get("source", "")
        content = doc.page_content
        
        # Code structure metadata
        code_meta = extract_code_metadata(full_path, content)
        doc.metadata.update(code_meta)
        
        # File role classification
        doc.metadata["file_role"] = classify_file_role(full_path, content)
        
        # Dependency tracking
        deps = extract_dependencies(full_path, content, all_file_paths)
        doc.metadata.update(deps)
    
    print("--- Metadata enrichment complete")
    return documents


def get_project_summary(documents: List[Document]) -> Dict[str, Any]:
    """
    Generate a high-level summary of the project from documents.
    
    Args:
        documents: All project documents
        
    Returns:
        Project summary dictionary
    """
    summary = {
        'total_files': len(set(doc.metadata.get('filename', '') for doc in documents)),
        'total_lines': sum(doc.metadata.get('line_count', 0) for doc in documents),
        'file_types': {},
        'roles': {},
        'main_technologies': set(),
        'key_classes': set(),
        'key_functions': set()
    }
    
    for doc in documents:
        # Count file types
        ext = doc.metadata.get('file_extension', 'unknown')
        summary['file_types'][ext] = summary['file_types'].get(ext, 0) + 1
        
        # Count roles
        role = doc.metadata.get('file_role', 'other')
        summary['roles'][role] = summary['roles'].get(role, 0) + 1
        
        # Collect key components
        if 'classes' in doc.metadata:
            summary['key_classes'].update(doc.metadata['classes'][:3])
        if 'functions' in doc.metadata:
            summary['key_functions'].update(doc.metadata['functions'][:3])
    
    # Limit sets
    summary['key_classes'] = list(summary['key_classes'])[:20]
    summary['key_functions'] = list(summary['key_functions'])[:20]
    
    return summary

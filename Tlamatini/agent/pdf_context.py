# Tlamatini Author Banner — Angela López Mendoza
"""PDF canvas ingestion: complete text and optional images for the normal RAG chain.

Uses the same PyMuPDF extraction capabilities as File-Interpreter complete mode,
without importing that executable agent (which changes cwd and configures logs).
All pages are included; optional previews preserve scans, inline images and vectors.
"""

from pathlib import Path
import re
import shutil
import threading
import uuid

from django.core import signing

from .path_guard import get_runtime_agent_root


_EXTRACTION_LOCK = threading.Lock()  # PyMuPDF is not safe across concurrent threads.
_TOKEN_SALT = "agent.pdf-canvas-context.v1"


class PdfContextError(ValueError):
    pass


class PdfContextCancelled(PdfContextError):
    pass


def _user_root(user_id):
    # The authenticated Django user id, never a client-provided path.
    return Path(get_runtime_agent_root()) / "context_files" / "pdf_canvas" / str(int(user_id))


def prepare_pdf_context(upload, user_id, password="", *, process_images=False,
                        cancelled=lambda: False, progress=lambda message: None):
    import pymupdf

    root = _user_root(user_id).resolve()
    document_id = uuid.uuid4().hex
    directory = root / document_id
    directory.mkdir(parents=True)
    source = directory / "source.pdf"
    index = directory / "document.txt"
    def check_cancelled():
        if cancelled():
            raise PdfContextCancelled("PDF context preparation cancelled.")
    try:
        # Django spools large multipart uploads to disk. Never read the entire
        # original into RAM or embed image bytes in the websocket/RAG prompt.
        with source.open("wb") as destination:
            for chunk in upload.chunks():
                check_cancelled()
                destination.write(chunk)
        with _EXTRACTION_LOCK, pymupdf.open(source) as document:
            if not document.is_pdf or not document.page_count:
                raise PdfContextError("The selected file is not a readable PDF.")
            if document.needs_pass and not document.authenticate(password):
                raise PdfContextError("The PDF password is missing or incorrect. Reopen and unlock the PDF first.")
            images = directory / "images"
            if process_images:
                images.mkdir()
            saved_images = {}
            has_text = False
            with index.open("w", encoding="utf-8") as text:
                text.write(f"PDF canvas context\nOriginal filename: {upload.name}\n")
                text.write(f"Original PDF: {source}\nPages: {document.page_count}\n")
                if process_images:
                    text.write("Mode: complete text and images (File-Interpreter equivalent).\n")
                    text.write("Each page preview and embedded image below is a local artifact available to Image-Interpreter.\n")
                else:
                    text.write("Mode: complete selectable text only. Image processing is disabled.\n")
                for page_number, page in enumerate(document, 1):
                    check_cancelled()
                    progress({'stage': 'extract', 'completed': page_number - 1, 'total': document.page_count,
                              'message': f'Extracting PDF page {page_number} of {document.page_count}…'})
                    text.write(f"\n--- Page {page_number} of {document.page_count} ---\n")
                    content = page.get_text(sort=True)
                    if content.strip():
                        has_text = True
                        text.write(content)
                    else:
                        text.write("[No selectable text; consult the page image.]\n" if process_images else
                                   "[No selectable text on this page. Enable Process images to interpret scanned content.]\n")
                    text.write("\n")
                    if not process_images:
                        continue
                    # Retain the visual page, including vectors, annotations,
                    # soft masks and inline images not exposed by get_images().
                    longest = max(page.rect.width, page.rect.height)
                    scale = min(2.0, 1600 / max(1, longest))
                    preview = images / f"page_{page_number:06d}.png"
                    page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(preview)
                    text.write(f"Page image: {preview}\n")
                    for entry in page.get_images(full=True):
                        xref = entry[0]
                        if not xref:
                            continue  # Already preserved in the rendered page.
                        if xref not in saved_images:
                            image = document.extract_image(xref)
                            if not image:
                                continue
                            extension = image.get("ext", "bin")
                            if not re.fullmatch(r"[A-Za-z0-9]+", extension):
                                extension = "bin"
                            target = images / f"embedded_{xref}.{extension}"
                            target.write_bytes(image["image"])
                            saved_images[xref] = target
                        text.write(f"Embedded image: {saved_images[xref]}\n")
            pages = document.page_count
        if not process_images and not has_text:
            raise PdfContextError('This PDF has no selectable text. Enable Process images and press Continue to read scanned pages.')
        analysis_count = 0
        analysis_failures = 0
        if process_images:
            # Release the PDF parser lock before network/model work. Reuse the
            # actual Image-Interpreter engine only when the user opts in.
            from .pdf_image_analysis import create_pdf_image_analyzer
            analyze = create_pdf_image_analyzer()
            with index.open('a', encoding='utf-8') as text:
                text.write('\n=== Image-Interpreter visual analyses ===\n')
                artifacts = sorted(images.iterdir())
                for number, artifact in enumerate(artifacts, 1):
                    check_cancelled()
                    progress({'stage': 'analyze', 'completed': number - 1, 'total': len(artifacts),
                              'message': f'Image-Interpreter: analyzing image {number} of {len(artifacts)}…'})
                    description, status = analyze(artifact)
                    check_cancelled()
                    report = artifact.with_suffix(artifact.suffix + '.analysis.txt')
                    report.write_text(f'Source image: {artifact}\nStatus: {status}\n\n{description}', encoding='utf-8')
                    text.write(f'\nSource image: {artifact}\nAnalysis report: {report}\nStatus: {status}\n{description}\n')
                    analysis_count += 1
                    if status != 'merged':
                        analysis_failures += 1
        check_cancelled()
        token = signing.dumps({"user": int(user_id), "document": document_id}, salt=_TOKEN_SALT)
        return {"token": token, "context_path": str(index), "context_filename": index.name,
                "pages": pages, "images": len(saved_images), "page_previews": pages if process_images else 0,
                "process_images": process_images,
                "analyses": analysis_count, "analysis_warnings": analysis_failures}
    except Exception:
        # Only remove the new, private package created by this request.
        resolved = directory.resolve()
        if resolved != root and resolved.is_relative_to(root):
            shutil.rmtree(resolved)
        raise


def resolve_pdf_context(token, user_id):
    """Accept only a signed package belonging to this authenticated user."""
    try:
        data = signing.loads(token, salt=_TOKEN_SALT)
        document_id = data["document"]
        if data["user"] != int(user_id) or not re.fullmatch(r"[a-f0-9]{32}", document_id):
            raise ValueError
        root = _user_root(user_id).resolve()
        directory = (root / document_id).resolve()
        if not directory.is_relative_to(root) or not (directory / "document.txt").is_file():
            raise ValueError
        return directory, "document.txt"
    except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
        raise PdfContextError("This PDF context is unavailable. Use Reopen and try again.") from error

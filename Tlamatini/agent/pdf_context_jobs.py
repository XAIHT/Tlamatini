# Tlamatini Author Banner — Angela López Mendoza
"""Bounded background jobs for PDF extraction and Image-Interpreter analysis."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time
import uuid

from django.core import signing
from django.core.files import File

from .path_guard import get_app_temp_root
from .pdf_context import PdfContextCancelled, prepare_pdf_context


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-context")
_lock = threading.Lock()
_jobs = {}
_salt = "agent.pdf-context-job.v1"


def _prune_jobs():
    for key, previous in list(_jobs.items()):
        if previous['status'] in {'complete', 'error', 'cancelled'} and time.monotonic() - previous['updated'] > 3600:
            del _jobs[key]


def cancel_request(request_id, user_id):
    """Cancel by a user-scoped upload id, including before multipart finishes."""
    key = (int(user_id), uuid.UUID(request_id).hex)
    with _lock:
        _prune_jobs()
        job = _jobs.setdefault(key, {'user': key[0], 'status': 'cancelled',
                                    'message': 'PDF context preparation cancelled.',
                                    'cancel': threading.Event(), 'updated': time.monotonic()})
        job['cancel'].set()
    return {'status': 'cancelling', 'message': 'PDF cancellation requested.'}


def start_job(upload, user_id, password="", request_id=None, *, process_images=False):
    job_id = uuid.UUID(request_id).hex if request_id else uuid.uuid4().hex
    token = signing.dumps({'job': job_id, 'user': int(user_id)}, salt=_salt)
    key = (int(user_id), job_id)
    job = {'user': int(user_id), 'status': 'pending', 'message': 'PDF queued for context preparation…',
           'cancel': threading.Event(), 'updated': time.monotonic()}
    with _lock:
        _prune_jobs()
        if key in _jobs:
            # A cancelled upload may reach the server after its cancellation.
            if _jobs[key]['cancel'].is_set():
                return token
            raise ValueError('This PDF upload has already been submitted.')
        _jobs[key] = job
    upload_root = Path(get_app_temp_root()) / 'pdf_context_uploads'
    path = upload_root / f'{int(user_id)}-{job_id}.pdf'
    try:
        upload_root.mkdir(exist_ok=True)
        with path.open('wb') as output:
            for chunk in upload.chunks():
                if job['cancel'].is_set():
                    raise PdfContextCancelled('PDF upload cancelled.')
                output.write(chunk)
    except PdfContextCancelled:
        path.unlink(missing_ok=True)
        with _lock:
            job.update(status='cancelled', message='PDF upload cancelled.', updated=time.monotonic())
        return token
    except Exception:
        path.unlink(missing_ok=True)
        with _lock:
            job.update(status='error', message='PDF upload failed.', updated=time.monotonic())
        raise

    def progress(detail):
        with _lock:
            job.update(detail, updated=time.monotonic())

    def run():
        try:
            with path.open('rb') as raw:
                result = prepare_pdf_context(File(raw, name=upload.name), user_id, password,
                                             process_images=process_images, cancelled=job['cancel'].is_set, progress=progress)
            with _lock:
                job.update(status='complete', result=result, message='PDF context is ready.')
        except PdfContextCancelled:
            with _lock:
                job.update(status='cancelled', message='PDF context preparation cancelled.')
        except Exception as error:
            with _lock:
                job.update(status='error', message=f'Could not prepare PDF context: {error}')
        finally:
            path.unlink(missing_ok=True)
            with _lock:
                job['updated'] = time.monotonic()
    _executor.submit(run)
    return token


def job_status(token, user_id, *, cancel=False):
    try:
        data = signing.loads(token, salt=_salt, max_age=86400)
        if data['user'] != int(user_id):
            raise ValueError
        with _lock:
            job = _jobs[(int(user_id), data['job'])]
            if job['user'] != int(user_id):
                raise ValueError
            if cancel:
                job['cancel'].set()
            return {key: job[key] for key in ('status', 'message', 'stage', 'completed', 'total', 'result') if key in job}
    except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
        raise ValueError('PDF context job is unavailable. Use Reopen and try again.') from error

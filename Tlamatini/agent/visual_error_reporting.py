# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Per-request visual-error reporting, independent of execution/recovery policy."""
from contextvars import ContextVar
import logging
import uuid


_sink = ContextVar('tlamatini_visual_error_sink', default=None)


def bind_visual_error_sink(emit):
    return _sink.set(emit)


def unbind_visual_error_sink(token):
    _sink.reset(token)


def report_visual_error(source, message):
    event = {'id': uuid.uuid4().hex, 'kind': 'fatal_visual_error',
             'source_agent': source, 'message': str(message)}
    logging.getLogger(__name__).critical('%s: %s', source, message)
    emit = _sink.get()
    if emit is not None:
        try:
            emit(event)
        except Exception:
            logging.getLogger(__name__).exception('Could not deliver visual error dialog event')
    return event

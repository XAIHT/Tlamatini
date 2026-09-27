# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Report a failed visual-analysis attempt without controlling recovery or retries.

Standalone agents use the existing runtime notification delivery channel. The
browser accumulates these events in its shared, themed, non-modal error dialog.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import uuid


def publish_visual_error(directory, source, error, *, secrets=()):
    message = str(error)
    for secret in secrets:
        if secret:
            message = message.replace(str(secret), '[redacted]')
    event = {
        'id': uuid.uuid4().hex, 'kind': 'fatal_visual_error',
        'source_agent': source, 'message': message,
        'outcome_detail': message, 'matches': ['FATAL'], 'sound_enabled': True,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    root = Path(directory)
    destination = root / 'notification.json'
    previous = json.loads(destination.read_text(encoding='utf-8')) if destination.is_file() else {}
    errors = previous.get('errors', []) if previous.get('kind') == 'fatal_visual_error' else []
    envelope = dict(event, errors=[*errors, event])
    temporary = root / ('notification-' + event['id'] + '.tmp')
    temporary.write_text(json.dumps(envelope, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, destination)
    return event

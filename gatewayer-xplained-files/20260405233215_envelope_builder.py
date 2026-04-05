
def build_event_envelope(handler, body_bytes: bytes, config: dict) -> dict:
    event_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    
    envelope = {
        'event_id': event_id,
        'received_at': now,
        'event_type': event_type,
        'session_id': session_id,
        'correlation_id': '',
        'body_hash': body_hash,
        'content_type': 'application/json' if parsed_body else 'text/plain',
        'method': 'HTTP_POST',
        'path': handler.path,
        'query_params': query_params,
        'headers': headers_dict,
        'body': parsed_body if parsed_body else body_text,
        'raw_body': body_text,
    }
    return envelope


def validate_request(handler, body_bytes: bytes, config: dict) -> str | None:
    payload_cfg = config.get('payload', {})
    
    # Content-Type validation
    content_type = handler.headers.get('Content-Type', '')
    accepted = payload_cfg.get('accepted_content_types', [])
    if accepted and not any(ct in content_type for ct in accepted):
        return f"Unsupported Content-Type: {content_type}"
    
    # Size limit validation
    max_bytes = payload_cfg.get('max_body_bytes', 1_048_576)
    if len(body_bytes) > max_bytes:
        return f"Payload too large: {len(body_bytes)} > {max_bytes}"
    
    # Required fields validation
    required_fields = payload_cfg.get('required_fields', [])
    if required_fields and 'json' in content_type:
        body_obj = json.loads(body_bytes)
        for field in required_fields:
            if field not in body_obj:
                return f"Missing required field: {field}"
    
    return None  # Valid

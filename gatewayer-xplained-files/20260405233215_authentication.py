
def authenticate_request(handler, auth_cfg: dict) -> bool:
    mode = auth_cfg.get('mode', 'none')
    
    # IP allowlist check (always applied if configured)
    allowed_ips = auth_cfg.get('allowed_ips', [])
    if allowed_ips:
        client_ip = handler.client_address[0]
        if client_ip not in allowed_ips:
            return False
    
    if mode == 'none':
        return True
    
    if mode == 'bearer':
        expected_token = auth_cfg.get('bearer_token', '')
        header_name = auth_cfg.get('header_name', 'Authorization')
        auth_value = handler.headers.get(header_name, '')
        return auth_value == f"Bearer {expected_token}"
    
    if mode == 'hmac':
        # HMAC signature validation with timestamp
        secret = auth_cfg.get('hmac_secret', '')
        # ... signature verification logic

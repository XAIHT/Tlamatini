
def persist_event(envelope: dict, config: dict):
    storage_cfg = config.get('storage', {})
    output_dir = storage_cfg.get('output_dir', 'gateway_events')
    
    event_id = envelope['event_id']
    event_dir = os.path.join(output_dir, event_id)
    os.makedirs(event_dir, exist_ok=True)
    
    # Write event.json
    if storage_cfg.get('write_event_json', True):
        with open(os.path.join(event_dir, 'event.json'), 'w') as f:
            json.dump(envelope, f, indent=2)
    
    # Write request_body.txt
    if storage_cfg.get('write_request_body', True):
        with open(os.path.join(event_dir, 'request_body.txt'), 'w') as f:
            f.write(envelope.get('raw_body', ''))
    
    # Write headers.json
    if storage_cfg.get('write_headers_json', True):
        with open(os.path.join(event_dir, 'headers.json'), 'w') as f:
            json.dump(envelope.get('headers', {}), f, indent=2)

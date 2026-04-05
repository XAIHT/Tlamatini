
def folder_watch_loop(config: dict):
    """Poll a directory for new files and enqueue them as events."""
    fw_cfg = config.get('folder_watch', {})
    watch_path = fw_cfg.get('watch_path', '')
    pattern = fw_cfg.get('file_pattern', '*.json')
    poll_interval = fw_cfg.get('poll_interval', 2)
    
    while not shutdown_event.is_set():
        files = [f for f in os.listdir(watch_path) 
                 if fnmatch.fnmatch(f, pattern)]
        
        for fname in sorted(files):
            fpath = os.path.join(watch_path, fname)
            with open(fpath, 'rb') as f:
                body_bytes = f.read()
            
            # Build envelope with method='FILE_DROP'
            envelope = build_event_envelope(...)
            persist_event(envelope, config)
            event_queue.put(envelope)
            
            # Archive if configured
            if fw_cfg.get('archive_processed', True):
                shutil.move(fpath, processed_dir)
        
        shutdown_event.wait(poll_interval)

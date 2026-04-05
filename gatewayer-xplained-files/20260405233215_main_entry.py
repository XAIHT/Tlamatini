
def main():
    config = load_config()
    
    logging.info("GATEWAYER AGENT STARTED")
    logging.info(f"Listen mode: {listen_mode}")
    logging.info(f"Targets: {target_agents}")
    
    # Restore reanim state
    restored_queue = load_reanim_queue()
    for ev in restored_queue:
        event_queue.put(ev)
    
    # Cleanup old events
    cleanup_old_events(config)
    
    # Signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    # Start dispatch loop thread
    dispatch_thread = threading.Thread(target=dispatch_loop, args=(config,), daemon=True)
    dispatch_thread.start()
    
    # Start folder watch thread if enabled
    if fw_cfg.get('enabled', False):
        fw_thread = threading.Thread(target=folder_watch_loop, args=(config,), daemon=True)
        fw_thread.start()
    
    # Start HTTP server if enabled
    if http_cfg.get('enabled', True):
        server = HTTPServer((host, port), GatewayerHandler)
        server.serve_forever()


def dispatch_loop(config: dict):
    """Background thread: drain event queue and start target_agents."""
    target_agents = config.get('target_agents', [])
    idle_ms = config.get('runtime', {}).get('idle_sleep_ms', 250)
    
    while not shutdown_event.is_set():
        try:
            envelope = event_queue.get(timeout=idle_ms/1000.0)
        except queue.Empty:
            continue
        
        event_id = envelope.get('event_id', '?')
        
        # Wait for previous targets to stop (concurrency guard)
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"GATEWAY_EVENT_DISPATCHED event_id={event_id}")
            for target in target_agents:
                start_agent(target)
        
        # Update reanim snapshot
        _persist_queue_snapshot()

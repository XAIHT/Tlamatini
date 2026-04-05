
def _log_event_payload(envelope: dict):
    """Log accepted event payload in two formats:
    
    1. Flat key-value lines (MESSAGE_<KEY>: <VALUE>) for Forker pattern matching
    2. Structured output block (INI_GATEWAY_EVENT<<< ... >>>END_GATEWAY_EVENT) 
       for Parametrizer and Summarizer
    """
    event_id = envelope.get('event_id', '')
    body = envelope.get('body')
    
    # Format 1: Flat key-value lines
    if isinstance(body, dict):
        for key, value in body.items():
            logging.info(f"MESSAGE_{key.upper()}: {value}")
    
    # Format 2: Structured block
    logging.info("INI_GATEWAY_EVENT<<<")
    logging.info(f"event_id: {event_id}")
    # ... additional fields
    logging.info(">>>END_GATEWAY_EVENT")

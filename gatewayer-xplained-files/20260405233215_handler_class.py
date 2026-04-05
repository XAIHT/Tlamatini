
class GatewayerHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, body: dict):
        raw = json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    
    def do_POST(self):
        self._handle_request()
    
    def do_PUT(self):
        self._handle_request()
    
    def do_PATCH(self):
        self._handle_request()
    
    def _handle_request(self):
        body_bytes = self._read_body()
        
        # Authenticate
        if not authenticate_request(self, auth_cfg):
            self._send_json(401, {'status': 'rejected', 'reason': 'auth_failed'})
            return
        
        # Validate
        error = validate_request(self, body_bytes, config)
        if error:
            self._send_json(400, {'status': 'rejected', 'reason': error})
            return
        
        # Build envelope and enqueue
        envelope = build_event_envelope(self, body_bytes, config)
        persist_event(envelope, config)
        _log_event_payload(envelope)
        
        # Queue overflow check
        if event_queue.qsize() >= max_pending:
            if overflow == 'reject_new':
                self._send_json(500, {'status': 'rejected', 'reason': 'queue_full'})
                return
        
        event_queue.put(envelope)
        self._send_json(200, {'status': 'accepted', 'event_id': event_id})

Tlamatini (2026/04/05 17:32:15.327)

# Detailed Source Code Summary: Gatewayer Agent Project

## Project Overview

The Gatewayer Agent is an inbound gateway agent that receives external events via HTTP webhook or folder-drop, validates them, normalizes the data, persists to disk, and dispatches to downstream target agents.

---

## File Structure

| File | Type | Purpose |
|------|------|---------|
| config.yaml | Configuration | Agent settings and parameters |
| gatewayer.py | Python Script | Main agent implementation (969 lines) |

---

## Configuration (config.yaml)

### Core Settings
- source_agents / target_agents: Connection fields for canvas-based agent flow wiring
- listen_mode: Primary ingress channel - "http_webhook" or "folder_watch"

### HTTP Webhook Ingress
  yaml:
http:
  enabled: true
  host: "127.0.0.1"
  port: 8787
  path: "/gatewayer"
  methods: ["POST"]
  use_tls: false
  request_timeout_sec: 15


### Folder-Drop Watcher Ingress
  yaml:
folder_watch:
  enabled: false
  watch_path: ""
  file_pattern: "*.json"
  poll_interval: 2
  archive_processed: true
  processed_dir: "processed"


### Authentication Modes
- mode: "bearer", "hmac", or "none"
- bearer_token: Token for Bearer authentication
- allowed_ips: IP allowlist
- hmac_secret: Secret for HMAC signature validation
- max_clock_skew_sec: Timestamp tolerance (300 seconds default)

### Payload Handling
- accepted_content_types: application/json, text/plain, application/x-www-form-urlencoded
- max_body_bytes: Maximum payload size (default 1MB)
- required_fields: Mandatory JSON body fields
- parse_json: Auto-parse JSON bodies
- event_type_field: Field name for event type (event_type)
- session_id_field: Field name for session ID (session_id)

---

## Main Script (gatewayer.py)

### 1. Initialization & Environment Setup

---Load in canvas: 20260405233215_gatewayer_init.py---

### 2. PID Management

---Load in canvas: 20260405233215_pid_management.py---

### 3. Reanimation State Persistence

The agent supports crash recovery through reanimation files:

---Load in canvas: 20260405233215_reanim_helpers.py---

### 4. Global State Variables

---Load in canvas: 20260405233215_global_state.py---

### 5. Authentication Module

---Load in canvas: 20260405233215_authentication.py---

### 6. Request Validation

---Load in canvas: 20260405233215_validation.py---

### 7. Event Envelope Builder

---Load in canvas: 20260405233215_envelope_builder.py---

### 8. Payload Logging for Downstream Agents

---Load in canvas: 20260405233215_payload_logging.py---

### 9. Event Persistence

---Load in canvas: 20260405233215_persistence.py---

### 10. Folder Watch Loop

---Load in canvas: 20260405233215_folder_watch.py---

### 11. Dispatch Loop

---Load in canvas: 20260405233215_dispatch_loop.py---

### 12. GatewayerHandler Class (HTTP Server)

---Load in canvas: 20260405233215_handler_class.py---

### 13. Agent Management Functions

---Load in canvas: 20260405233215_agent_management.py---

### 14. Old Event Cleanup

---Load in canvas: 20260405233215_cleanup.py---

### 15. Main Entry Point

---Load in canvas: 20260405233215_main_entry.py---

---

## Data Flow Summary




Stage	Component	Action
1. Ingress	HTTP Webhook / Folder Watch	Receive external event
2. Authentication	authenticate_request()	Validate bearer token / HMAC / IP
3. Validation	validate_request()	Check content-type, size, required fields
4. Normalization	build_event_envelope()	Create canonical event structure
5. Persistence	persist_event()	Write event.json, request_body.txt, headers.json
6. Logging	_log_event_payload()	Log for downstream agents (Forker, Summarizer)
7. Queuing	event_queue.put()	Add to in-memory queue with overflow handling
8. Dispatch	dispatch_loop()	Drain queue and start target agents
9. Execution	start_agent()	Launch downstream agent subprocess




---

## Key Design Patterns

1. Thread-Based Architecture: Separate threads for HTTP server, folder watch, and dispatch loop
2. Graceful Shutdown: Signal handlers set shutdown_event to stop all threads cleanly
3. Crash Recovery: Reanimation files persist queue state across restarts
4. Concurrency Control: Waits for target agents to stop before dispatching new events
5. Dual Logging Format: Flat key-value lines for Forker, structured blocks for Summarizer/Parametrizer
6. PID-Based Process Management: Uses PID files and psutil for agent lifecycle tracking




shutdown_event = threading.Event()
event_queue: queue.Queue = queue.Queue()
_gatewayer_config: dict = {}
_gatewayer_log_cfg: dict = {}

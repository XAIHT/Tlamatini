
REANIM_QUEUE_FILE = "reanim_queue.json"
REANIM_DEDUP_FILE = "reanim_dedup.json"

def save_reanim_queue(events: list):
    with open(REANIM_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False)

def load_reanim_queue() -> list:
    # Returns queued events from previous run


def cleanup_old_events(config: dict):
    """Remove events older than keep_days."""
    storage_cfg = config.get('storage', {})
    keep_days = storage_cfg.get('keep_days', 7)
    if keep_days <= 0:
        return
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    # Iterate event directories and remove old ones

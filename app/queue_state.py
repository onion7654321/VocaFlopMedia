"""Queue action and completion rules shared by the desktop interface."""


def queue_action(items):
    items = tuple(items)
    if any(item.busy for item in items):
        enabled = any(item.busy and item.status not in {"Stopping...", "Cancelling..."} for item in items)
        return "Stop all", enabled
    if any(item.status == "Stopped" for item in items):
        return "Resume all", True
    return None, False


def ready_to_shutdown(items, results, pending=0, dispatches=0):
    return (not pending and not dispatches and bool(results)
            and all(status == "Completed" for status in results.values())
            and not any(item.busy or item.status == "Stopped" for item in items))

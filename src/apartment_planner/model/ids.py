import uuid


def new_id() -> str:
    """Return a new random ID for any persistent entity."""
    return uuid.uuid4().hex

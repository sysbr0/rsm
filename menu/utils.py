# cloud_menu/utils.py  (and mirror it in local_app/utils.py)
import uuid


def generate_uuid_str() -> str:
    """Return a UUID4 as a 36-char hyphenated string."""
    return str(uuid.uuid4())
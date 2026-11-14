import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid4().hex}"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class Problem(Exception):
    def __init__(self, code, message, status=409, **details):
        self.code, self.message, self.status, self.details = code, message, status, details
        super().__init__(message)

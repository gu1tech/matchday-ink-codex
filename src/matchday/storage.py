"""Atomic JSON persistence shared by core and optional integrations."""

import json
import os
from pathlib import Path
from uuid import uuid4


def write_json(path, data, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if private:
        path.parent.chmod(0o700)
    temporary = path.with_suffix("." + uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, ensure_ascii=True)
    temporary.replace(path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default



import copy
import json
import os
import tempfile
import threading
from pathlib import Path

# Satu lock untuk seluruh proses agar penulisan file tidak bentrok.
LOCK = threading.RLock()


def read_json(path, default):
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data):
    """Tulis atomik: tulis ke file sementara lalu ganti (os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise

#!/usr/bin/env python3
"""
Atomic write - a file replaced in one step, never left half-written.

token.json (a channel's YouTube connection) and upload_schedule.json are
rewritten while other threads read them, and uvicorn --reload can stop the
server in the middle of a write: written directly, a crash leaves an empty
or truncated file (the channel must be reconnected, the schedule is lost).
"""

import os
import threading


def write_file_atomic(path: str, text: str):
    """Writes next to the file (a .part unique to this thread) then moves it
    over the old one in one step (os.replace): a crash or a restart while
    writing, or two threads refreshing the same token at once, never leave a
    half-written token.json (the channel would have to be reconnected) or
    schedule file — at worst the previous version stays."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

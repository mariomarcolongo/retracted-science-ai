"""Crash-safe reading of the append-only run logs (D65).

Usage: from logfiles import read_log; records, note = read_log(path)

Each log line is written in one call and flushed to disk, so a crash can leave at most one incomplete line, at
the end. read_log moves such a tail to <path>.partial-<UTC time>, cuts the log back to its last complete line,
and returns a note saying so; the caller logs the note as an event. Nothing else is repaired: an invalid
complete line anywhere stops the run. With repair=False (a log written by another step) an incomplete tail
stops the run instead, with a message naming the step to resume first.

Writing (D66): Appender.write(path, record) appends one line with low-level writes and fsync. If a line cannot be
written in full (disk full, I/O error), the bytes of that line are cut off again where possible, and every later
write of the process raises WriteFailed, so nothing is ever appended after a broken line; the step stops and is
resumed later. write_json(path, obj) replaces a small JSON file in one step (temporary file + rename).
"""
import datetime
import json
import os
import threading


class WriteFailed(Exception):
    """A log line could not be written in full; the step stops and writes nothing more."""


class Appender:
    def __init__(self):
        self.lock = threading.Lock()
        self.failed = None

    def write(self, path, record):
        line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            if self.failed:
                raise WriteFailed(self.failed)
            fd = size = None
            try:
                fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
                size = os.fstat(fd).st_size
                view = memoryview(line)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            except OSError as e:
                self.failed = f"could not write {os.path.basename(path)}: {e}"
                if fd is not None and size is not None:
                    try:
                        os.ftruncate(fd, size)
                        os.fsync(fd)
                    except OSError:
                        pass  # the incomplete tail is moved aside by read_log on the next start
                raise WriteFailed(self.failed) from e
            finally:
                if fd is not None:
                    os.close(fd)


def write_json(path, obj, **kw):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, **kw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_log(path, repair=True, owner="the step that writes it"):
    if not os.path.exists(path):
        return [], None
    with open(path, "rb") as stream:
        data = stream.read()
    note = None
    if data and not data.endswith(b"\n"):
        cut = data.rfind(b"\n") + 1
        if not repair:
            raise SystemExit(f"{path} ends with an incomplete line (a crash while writing); resume {owner} first")
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        side = f"{path}.partial-{stamp}"
        with open(side, "wb") as stream:
            stream.write(data[cut:])
            stream.flush()
            os.fsync(stream.fileno())
        with open(path, "r+b") as stream:
            stream.truncate(cut)
            stream.flush()
            os.fsync(stream.fileno())
        note = f"incomplete last line ({len(data) - cut} bytes) moved to {os.path.basename(side)}"
        data = data[:cut]
    records = []
    for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            raise SystemExit(f"{path} line {number} is not valid JSON; it is not repaired automatically")
    return records, note

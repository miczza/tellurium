"""Split the integration test files into CI shards of similar duration.

``python -m tests.shard <n> <count> [dir]`` prints the files of shard *n*
(1-based) of *count*. Each file weighs its seconds in
``<dir>/durations.json`` (the slowest system of a CI run; refresh it from
the JUnit reports when the suite changes), a file not listed weighs the
median. The heaviest file goes to the lightest shard first, so a shard ends
near the total divided by *count* unless one file alone is longer.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

DEFAULT_DIR = Path(__file__).parent / "integration"


def weight(file: str, durations: dict[str, float]) -> float:
    name = Path(file).name
    if name in durations:
        return durations[name]
    return statistics.median(durations.values()) if durations else 1.0


def files_of(n: int, count: int, files: list[str], durations: dict[str, float]) -> list[str]:
    """The files of shard *n* (1-based) of *count*, sorted."""
    load = [0.0] * count
    mine: list[list[str]] = [[] for _ in range(count)]
    for file in sorted(files, key=lambda f: (-weight(f, durations), f)):
        lightest = load.index(min(load))
        load[lightest] += weight(file, durations)
        mine[lightest].append(file)
    return sorted(mine[n - 1])


def main(argv: list[str]) -> None:
    n, count = int(argv[0]), int(argv[1])
    folder = Path(argv[2]) if len(argv) > 2 else DEFAULT_DIR
    durations_file = folder / "durations.json"
    durations = json.loads(durations_file.read_text()) if durations_file.exists() else {}
    files = [p.as_posix() for p in sorted(folder.glob("test_*.py"))]
    # Bytes, not text: a text stdout on Windows ends lines with "\r\n", and
    # bash's $(...) keeps the "\r" in the file names.
    sys.stdout.flush()
    sys.stdout.buffer.write(("\n".join(files_of(n, count, files, durations)) + "\n").encode())
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main(sys.argv[1:])

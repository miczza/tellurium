"""Whether macOS's ``pthread_rwlock_t`` alone can leave writers parked on a
lock nobody holds, outside Chrome.

Chrome's browser process was seen with two writers parked on BoringSSL's pool
lock and no holder in sight (run 43001946271). This drives one rwlock the way
that pool is driven (short write sections from several threads, readers in
between) in a C program, with a watchdog: a lock that makes no progress for
``STALL`` seconds while every thread waits on it is a stall of the system's
lock itself. Not part of the suite: run it by path on a macOS runner
(``-f tests=tests/integration/rwlock_stress.py``).
"""

from __future__ import annotations

import os
import select
import shutil
import subprocess
import sys

import pytest

from tests.blocked_locks import rwlocks
from tests.process_snapshot import snapshot

SECONDS = int(os.environ.get("TELLURIUM_RWLOCK_SECONDS", "240"))
STALL = 5
#: How long the program gets past its run to join its threads and say how it went.
JOIN_GRACE = 30

_C = r"""
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static pthread_rwlock_t lock = PTHREAD_RWLOCK_INITIALIZER;
static atomic_ulong done;
static volatile int stop;

static void *worker(void *arg) {
    unsigned seed = (unsigned)(size_t)arg;
    while (!stop) {
        int write = rand_r(&seed) % 3 != 0;
        if (write ? pthread_rwlock_wrlock(&lock) : pthread_rwlock_rdlock(&lock)) abort();
        if (rand_r(&seed) % 64 == 0) usleep(rand_r(&seed) % 50);
        if (pthread_rwlock_unlock(&lock)) abort();
        atomic_fetch_add(&done, 1);
        if (rand_r(&seed) % 16 == 0) usleep(rand_r(&seed) % 200);
    }
    return NULL;
}

int main(int argc, char **argv) {
    int threads = atoi(argv[1]), seconds = atoi(argv[2]), stall = atoi(argv[3]);
    pthread_t t[64];
    for (int i = 0; i < threads; i++) pthread_create(&t[i], NULL, worker, (void *)(size_t)(i + 1));
    unsigned long last = 0;
    int still = 0;
    for (int s = 0; s < seconds; s++) {
        sleep(1);
        unsigned long now = atomic_load(&done);
        still = now == last ? still + 1 : 0;
        last = now;
        if (still >= stall) { printf("STALL after %lu sections\n", now); fflush(stdout); pause(); }
    }
    stop = 1;
    for (int i = 0; i < threads; i++) pthread_join(t[i], NULL);
    printf("ok %lu sections\n", atomic_load(&done));
    return 0;
}
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS's rwlock")
@pytest.mark.parametrize("threads", [4, 16])
def test_a_contended_rwlock_never_parks_its_writers_for_good(tmp_path, threads):
    cc = shutil.which("cc") or shutil.which("clang")
    assert cc, "no C compiler"
    src, exe = tmp_path / "stress.c", tmp_path / "stress"
    src.write_text(_C)
    subprocess.run([cc, "-O2", "-o", str(exe), str(src)], check=True)
    cmd = [str(exe), str(threads), str(SECONDS // 2), str(STALL)]
    print(_outcome(cmd, deadline=SECONDS // 2 + JOIN_GRACE))


def _outcome(cmd: list[str], deadline: float) -> str:
    """The first line the stress prints within *deadline*, ``ok ...``; a stall
    or silence (a final join that never ends) fails the test with the
    program's snapshot. The program never outlives this."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([proc.stdout], [], [], deadline)
        first = proc.stdout.readline() if ready else ""  # a whole line, flushed by the program
        if not first.startswith("ok"):
            what = first.strip() or f"no word in {deadline:g}s (exit code {proc.poll()})"
            pytest.fail(f"{what}\n{_report(proc.pid)}")
        return first.strip()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(10)
        proc.stdout.close()


def _report(pid: int) -> str:
    """Where the program's threads are, and who holds the lock they wait on."""
    text = snapshot(pid)
    return f"{text}\n{rwlocks(pid, text)}"

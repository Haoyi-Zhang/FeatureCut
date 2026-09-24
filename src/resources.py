"""Single-worker experimental envelope. No probes or network access."""
import os
import resource
import time


def begin(cpu_limit: int = 35):
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    cap = 3 * 1024**3
    old = resource.getrlimit(resource.RLIMIT_AS)[0]
    cap = min(cap, old) if old > 0 else cap
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    # Absolute process CPU limit includes interpreter startup, comfortably above
    # measured bounded chunks, and far below the campaign's per-run ceiling.
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
    return time.process_time(), time.perf_counter()


def finish(start):
    return {'cpu_seconds': time.process_time() - start[0],
            'wall_seconds': time.perf_counter() - start[1],
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'workers': 1, 'address_space_limit_bytes': 3 * 1024**3}

"""Utilities for concurrent execution (e.g. ProcessPoolExecutor)."""

from typing import Optional


# Default cap for max_workers (applied on all platforms).
DEFAULT_MAX_WORKERS_CAP = 60
# Default cores to reserve for OS/UI when computing worker count.
DEFAULT_RESERVED_CORES = 2


def get_process_pool_max_workers(cpu_count: Optional[int], config: Optional[dict] = None) -> int:
    """Return effective max_workers for ProcessPoolExecutor from cpu count and config.

    Computes desired workers as max(1, cpu_count - reserved_cores), then applies
    the configurable cap (parallel_processing.process_pool.max_workers_cap).
    Both reserved_cores and max_workers_cap are read from config.

    Args:
        cpu_count: Number of CPUs (e.g. from os.cpu_count()). If None, 4 is used.
        config: Application config dict. If None or keys missing, defaults are used.

    Returns:
        Effective max_workers: min(desired, cap), at least 1.
    """
    pool_config = (config or {}).get('parallel_processing', {}).get('process_pool', {})
    cores = cpu_count if cpu_count is not None else 4
    reserved = pool_config.get('reserved_cores')
    if reserved is None:
        reserved = DEFAULT_RESERVED_CORES
    desired = max(1, cores - reserved)
    cap = pool_config.get('max_workers_cap')
    if cap is None:
        cap = DEFAULT_MAX_WORKERS_CAP
    effective = min(desired, cap)
    return max(1, effective)

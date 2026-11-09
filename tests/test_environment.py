"""The environment of the test run itself."""

import os

import pytest


def test_numerical_libraries_use_one_thread_per_worker():
    """Workers must not each start a thread per CPU thread, nor a serial run saturate the CPU (see conftest.py)."""
    threadpoolctl = pytest.importorskip('threadpoolctl')
    import numpy  # noqa: F401  (loads OpenBLAS)
    pools = threadpoolctl.threadpool_info()
    # One per worker in parallel runs; at most half the CPU threads in serial ones
    limit = 1 if os.environ.get('PYTEST_XDIST_WORKER') else max(1, (os.cpu_count() or 2) // 2)
    assert pools and all(pool['num_threads'] <= limit for pool in pools), pools


class FakeConfig:
    def __init__(self, markexpr):
        self.option = type('Option', (), {'markexpr': markexpr})()


def test_workers_spare_cpu_and_memory(monkeypatch):
    """-n auto: at most half the CPU threads, within the free memory; serial with the slow tests."""
    import conftest
    psutil = pytest.importorskip('psutil')
    workers = conftest.pytest_xdist_auto_num_workers(FakeConfig('not slow'))
    assert workers == 0 or 2 <= workers <= (os.cpu_count() or 2) // 2

    # Little free memory: fewer workers, or a serial run
    memory = type('Memory', (), {'available': conftest.MEMORY_MARGIN + 2.5 * conftest.WORKER_MEMORY})()
    monkeypatch.setattr(psutil, 'virtual_memory', lambda: memory)
    assert conftest.pytest_xdist_auto_num_workers(FakeConfig('not slow')) in (0, 2)
    memory.available = conftest.MEMORY_MARGIN
    assert conftest.pytest_xdist_auto_num_workers(FakeConfig('not slow')) == 0


@pytest.mark.parametrize('expression, slow', [('not slow', False), ('slow', True), ('slow or not slow', True),
                                              ('data and not slow', False), ('', True)])
def test_slow_tests_run_serially(expression, slow):
    import conftest
    assert conftest.selectsSlowTests(FakeConfig(expression)) == slow
    if slow:
        assert conftest.pytest_xdist_auto_num_workers(FakeConfig(expression)) == 0

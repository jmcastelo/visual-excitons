"""Background tasks: worker thread, progress, cancellation and the hooks into yambopy."""

import threading
import time

import pytest

from visual_excitons.core.tasks import TaskRunner, TaskContext, Cancelled, currentContext, databaseAccess, DATABASE_LOCK

TIMEOUT = 5000  # ms


@pytest.fixture
def runner(qtbot):
    r = TaskRunner()
    yield r
    r.cancelAll()
    qtbot.waitUntil(lambda: not r.isBusy(), timeout=TIMEOUT)
    r.waitForDone(TIMEOUT)


def test_compute_in_worker_apply_in_gui_thread(qtbot, runner):
    threads = {}

    def compute(context):
        threads['compute'] = threading.current_thread()
        assert currentContext() is context
        return 21

    def apply(result):
        threads['apply'] = threading.current_thread()
        threads['result'] = result * 2

    with qtbot.waitSignal(runner.busyChanged, timeout=TIMEOUT, check_params_cb=lambda busy: not busy):
        runner.submit('Working…', compute, apply)
    assert threads['compute'] is not threading.main_thread()
    assert threads['apply'] is threading.main_thread()
    assert threads['result'] == 42 and currentContext() is None


def test_tasks_run_in_order(qtbot, runner):
    order = []
    for i in range(4):
        runner.submit(f'Task {i}', lambda context, i=i: (time.sleep(0.01), i)[1], order.append)
    qtbot.waitUntil(lambda: len(order) == 4, timeout=TIMEOUT)
    assert order == [0, 1, 2, 3]


def test_progress(qtbot, runner):
    reports = []
    runner.progress.connect(lambda done, total, stage: reports.append((done, total, stage)))

    def compute(context):
        context.stage('Counting', 3)
        for _ in range(3):
            context.advance()

    with qtbot.waitSignal(runner.finished, timeout=TIMEOUT):
        runner.submit('Working…', compute, lambda result: None)
    # Throttled, but the start and the end of a stage are always reported
    assert reports[0] == (0, 3, 'Counting') and reports[-1] == (3, 3, 'Counting')


def test_cancel_stops_the_running_task_and_drops_the_queue(qtbot, runner):
    started = threading.Event()
    applied, cancelled = [], []
    runner.cancelled.connect(cancelled.append)

    def slow(context):
        started.set()
        while True:
            context.advance()
            time.sleep(0.005)

    runner.submit('Slow…', slow, applied.append)
    runner.submit('Queued…', lambda context: 1, applied.append)
    assert started.wait(TIMEOUT / 1000)
    assert runner.queuedCount() == 1

    with qtbot.waitSignal(runner.busyChanged, timeout=TIMEOUT, check_params_cb=lambda busy: not busy):
        runner.cancelAll()
    assert cancelled == ['Slow…'] and applied == [] and not runner.isBusy()


def test_newer_task_with_the_same_key_replaces_the_queued_one(qtbot, runner):
    release = threading.Event()
    applied = []
    runner.submit('Blocker…', lambda context: release.wait(TIMEOUT / 1000), lambda result: None)
    for value in (1, 2, 3):
        runner.submit('Recompute…', lambda context, value=value: value, applied.append, key='recompute')
    runner.submit('Other…', lambda context: 'other', applied.append, key='other')
    assert runner.queuedCount() == 2
    release.set()
    qtbot.waitUntil(lambda: not runner.isBusy(), timeout=TIMEOUT)
    assert applied == [3, 'other']


def test_results_from_before_a_reset_are_discarded(qtbot, runner):
    release = threading.Event()
    applied = []
    # Ignores cancellation: finishes normally after the reset
    runner.submit('Old dataset…', lambda context: release.wait(TIMEOUT / 1000) and 'old', applied.append)
    runner.reset()
    release.set()
    qtbot.waitUntil(lambda: not runner.isBusy(), timeout=TIMEOUT)
    runner.submit('New dataset…', lambda context: 'new', applied.append)
    qtbot.waitUntil(lambda: not runner.isBusy(), timeout=TIMEOUT)
    assert applied == ['new']


def test_failures_are_reported(qtbot, runner):
    def compute(context):
        raise ValueError('boom')

    with qtbot.waitSignal(runner.failed, timeout=TIMEOUT) as blocker:
        runner.submit('Computing the thing…', compute, lambda result: None)
    assert blocker.args == ['Computing the thing failed', 'boom']

    def badApply(result):
        raise RuntimeError('apply broke')

    with qtbot.waitSignal(runner.failed, timeout=TIMEOUT) as blocker:
        runner.submit('Applying…', lambda context: 1, badApply)
    assert blocker.args == ['Applying failed', 'apply broke']
    qtbot.waitUntil(lambda: not runner.isBusy(), timeout=TIMEOUT)


def test_synchronous_runner(qtbot):
    runner = TaskRunner(synchronous=True)
    applied = []
    with qtbot.waitSignals([runner.started, runner.finished]):
        runner.submit('Inline…', lambda context: threading.current_thread(), applied.append)
    assert applied == [threading.main_thread()] and not runner.isBusy()


def test_database_access_waits_for_the_running_task(qtbot, runner):
    inside, release = threading.Event(), threading.Event()

    def compute(context):
        inside.set()
        release.wait(TIMEOUT / 1000)

    runner.submit('Reading…', compute, lambda result: None)
    assert inside.wait(TIMEOUT / 1000)
    # The worker holds the lock while computing
    assert not DATABASE_LOCK.acquire(blocking=False)
    release.set()
    with databaseAccess():
        pass
    qtbot.waitUntil(lambda: not runner.isBusy(), timeout=TIMEOUT)


# Hooks into yambopy

def test_tqdm_hook_reports_and_cancels():
    import yambopy.dbs.wfdb as wfdb
    TaskRunner()  # installs the hooks

    # Outside a task: the real tqdm
    assert type(wfdb.tqdm(range(2), disable=True)).__name__ == 'tqdm'

    reports = []
    context = TaskContext(lambda done, total, stage: reports.append((done, total, stage)))
    from visual_excitons.core import tasks
    tasks._local.context = context
    try:
        assert list(wfdb.tqdm(range(3), desc='Loading Wavefunctions')) == [0, 1, 2]
        assert reports[0] == (0, 3, 'Loading the wave functions') and reports[-1] == (3, 3, 'Loading the wave functions')

        bar = wfdb.tqdm(total=4, desc='Ex-wf')
        bar.update(1)
        bar.set_postfix(anything=1)  # unknown methods are accepted
        bar.close()
        assert context.label == 'Real-space wave function' and context.done == 1

        context.cancel()
        with pytest.raises(Cancelled):
            list(wfdb.tqdm(range(3)))
    finally:
        tasks._local.context = None


def test_dispersion_hook_counts_databases(monkeypatch):
    import yambopy.bse.bse_dispersion as dispersion
    TaskRunner()
    hook = dispersion.YamboExcitonDB
    monkeypatch.setattr(hook, '_realClass', type('Fake', (), {'from_db_file': staticmethod(lambda *a, **k: 'db')}))

    from visual_excitons.core import tasks
    context = TaskContext()
    context.stage('Loading', 2)
    tasks._local.context = context
    try:
        assert hook.from_db_file('lattice', filename='x') == 'db'
        assert context.done == 1
    finally:
        tasks._local.context = None
    assert hook.from_db_file('lattice') == 'db'  # outside a task: just loads

"""
Slow calculations in a background thread, so the window stays responsive.

A task has two parts:

- compute(context): runs in the worker thread on a snapshot of its inputs. It
  must not touch the state shared with the GUI nor emit signals; it returns a
  result. It can report progress and is stopped by cancellation through
  `context` (see TaskContext).
- apply(result): runs back in the GUI thread, stores the result and emits the
  signals that update the plots.

Tasks run one at a time, in the order they were submitted: the Yambo databases
are read with netCDF/HDF5, which must not be used from two threads at once.
For the same reason, reads of the databases from the GUI thread go through
databaseAccess(). Submitting a task with a `key` drops the queued (not yet
started) tasks with that key: e.g. only the latest recalculation of the
absorption spectra runs.

Progress comes from hooks into yambopy: its tqdm progress bars (loading wave
functions, real-space exciton wave function) and the loading of one exciton
database per Q-point (dispersion). The hooks also check for cancellation, so
cancelled tasks stop within a fraction of a second.
"""

import threading
import time
import traceback
from collections import deque
from contextlib import contextmanager

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class Cancelled(Exception):
    """Raised inside a task when it has been cancelled."""


# Reading the databases: one thread at a time (reentrant: tasks hold it while computing)
DATABASE_LOCK = threading.RLock()


@contextmanager
def databaseAccess():
    """Read Yambo databases from the GUI thread; waits for the running task, if any."""
    with DATABASE_LOCK:
        yield


_local = threading.local()


def currentContext():
    """The TaskContext of the task running in this thread, or None."""
    return getattr(_local, 'context', None)


class TaskContext:
    """Progress reporting and cancellation, as seen from inside a task."""

    # Minimum interval between progress signals, in seconds
    PROGRESS_INTERVAL = 0.05

    def __init__(self, report=None):
        self._cancelled = threading.Event()
        self._report = report
        self._lastReport = 0.0
        self.label = ''
        self.total = 0
        self.done = 0

    def cancel(self):
        self._cancelled.set()

    def isCancelled(self):
        return self._cancelled.is_set()

    def check(self):
        """Stop here if the task was cancelled."""
        if self._cancelled.is_set():
            raise Cancelled()

    def stage(self, label, total=0):
        """Start a stage of the task: `total` steps, or 0 if unknown."""
        self.check()
        self.label, self.total, self.done = label, int(total or 0), 0
        self._send(force=True)

    def advance(self, steps=1):
        self.check()
        self.done += steps
        self._send(force=self.total > 0 and self.done >= self.total)

    def _send(self, force=False):
        now = time.monotonic()
        if self._report is not None and (force or now - self._lastReport >= self.PROGRESS_INTERVAL):
            self._lastReport = now
            self._report(self.done, self.total, self.label)


# Progress hooks into yambopy

# Readable names of yambopy's progress bars
STAGE_NAMES = {
    'Loading Wavefunctions': 'Loading the wave functions',
    'Loading Miller Indices': 'Loading the Miller indices',
    'Expanding Wavefunctions full BZ': 'Expanding the wave functions to the full Brillouin zone',
    'Ex-wf': 'Real-space wave function',
}


class _TaskProgressBar:
    """Stand-in for a tqdm bar inside a task: reports to the task instead of the console."""

    def __init__(self, context, iterable=None, desc=None, total=None, **kwargs):
        self.context = context
        self.iterable = iterable
        if total is None and iterable is not None and hasattr(iterable, '__len__'):
            total = len(iterable)
        context.stage(STAGE_NAMES.get(desc, desc or ''), total or 0)

    def __iter__(self):
        for item in self.iterable:
            self.context.check()
            yield item
            self.context.advance()

    def update(self, n=1):
        self.context.advance(n)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        # set_description, set_postfix, refresh...: nothing to do
        return lambda *args, **kwargs: None


def _hookedTqdm(realTqdm):
    def tqdm(*args, **kwargs):
        context = currentContext()
        if context is None:
            return realTqdm(*args, **kwargs)
        return _TaskProgressBar(context, *args, **kwargs)
    return tqdm


class _CountingExcitonDB:
    """Stand-in for YamboExcitonDB in the dispersion module: counts the databases loaded."""

    def __init__(self, realClass):
        self._realClass = realClass

    def from_db_file(self, *args, **kwargs):
        context = currentContext()
        if context is not None:
            context.check()
        result = self._realClass.from_db_file(*args, **kwargs)
        if context is not None:
            context.advance()
        return result

    def __getattr__(self, name):
        return getattr(self._realClass, name)


_hooksInstalled = False


def installProgressHooks():
    """Route yambopy's progress reporting to the running task (idempotent)."""
    global _hooksInstalled
    if _hooksInstalled:
        return
    import yambopy.dbs.wfdb as wfdb
    import yambopy.bse.realSpace_excitonwf as realSpace
    import yambopy.bse.bse_dispersion as dispersion
    for module in (wfdb, realSpace):
        module.tqdm = _hookedTqdm(module.tqdm)
    dispersion.YamboExcitonDB = _CountingExcitonDB(dispersion.YamboExcitonDB)
    _hooksInstalled = True


# Tasks and their runner

class Task:
    def __init__(self, message, compute, apply, key=None, generation=0):
        self.message = message
        self.compute = compute
        self.apply = apply
        self.key = key
        self.generation = generation
        self.context = None


class _Relay(QObject):
    """Carries results and progress from the worker thread to the GUI thread."""
    progress = Signal(object, int, int, str)  # task, done, total, label
    done = Signal(object, object, object)     # task, result, exception or None


class _Runnable(QRunnable):
    def __init__(self, task, relay):
        super().__init__()
        self.task = task
        self.relay = relay
        self.setAutoDelete(True)

    def run(self):
        task, relay = self.task, self.relay
        _local.context = task.context
        try:
            with DATABASE_LOCK:
                task.context.check()
                result = task.compute(task.context)
            relay.done.emit(task, result, None)
        except BaseException as error:
            if not isinstance(error, Cancelled):
                traceback.print_exc()
            relay.done.emit(task, None, error)
        finally:
            _local.context = None


class TaskRunner(QObject):
    """Runs tasks one at a time in a worker thread (or inline when synchronous)."""

    started = Signal(str)                 # message of the task starting
    progress = Signal(int, int, str)      # done, total (0: unknown), stage
    finished = Signal()                   # a task finished, failed or was cancelled
    failed = Signal(str, str)             # title, message
    cancelled = Signal(str)               # message of the cancelled task
    busyChanged = Signal(bool)

    def __init__(self, synchronous=False, parent=None):
        super().__init__(parent)
        installProgressHooks()
        self.synchronous = synchronous
        self.pending = deque()
        self.running = None
        # Results of tasks submitted before the last reset are discarded
        self.generation = 0

        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.relay = _Relay()
        self.relay.progress.connect(self._onProgress)
        self.relay.done.connect(self._onDone)

    def isBusy(self):
        return self.running is not None or bool(self.pending)

    def queuedCount(self):
        return len(self.pending)

    def submit(self, message, compute, apply, key=None):
        task = Task(message, compute, apply, key, self.generation)
        if key is not None:
            self.pending = deque(t for t in self.pending if t.key != key)
        wasBusy = self.isBusy()
        self.pending.append(task)
        if not wasBusy:
            self.busyChanged.emit(True)
        self._startNext()
        return task

    @Slot()
    def cancelAll(self):
        """Drop the queued tasks and stop the running one."""
        hadPending = bool(self.pending)
        self.pending.clear()
        if self.running is not None:
            # busyChanged(False) follows when it stops (see _onDone)
            self.running.context.cancel()
        elif hadPending:
            self.busyChanged.emit(False)

    @Slot()
    def reset(self):
        """Cancel everything and discard results still on their way (e.g. a new dataset)."""
        self.generation += 1
        self.cancelAll()

    def waitForDone(self, timeoutMs=-1):
        """Block until the worker is idle (tests, closing the window)."""
        return self.pool.waitForDone(timeoutMs)

    def _startNext(self):
        if self.running is not None or not self.pending:
            return
        task = self.pending.popleft()
        self.running = task
        task.context = TaskContext(lambda done, total, label: self.relay.progress.emit(task, done, total, label))
        self.started.emit(task.message)

        if self.synchronous:
            _local.context = task.context
            try:
                with DATABASE_LOCK:
                    result = task.compute(task.context)
                error = None
            except Exception as exception:
                if not isinstance(exception, Cancelled):
                    traceback.print_exc()
                result, error = None, exception
            finally:
                _local.context = None
            self._onDone(task, result, error)
        else:
            self.pool.start(_Runnable(task, self.relay))

    @Slot(object, int, int, str)
    def _onProgress(self, task, done, total, label):
        if task is self.running:
            self.progress.emit(done, total, label)

    @Slot(object, object, object)
    def _onDone(self, task, result, error):
        self.running = None
        title = task.message[:-1] if task.message.endswith('…') else task.message

        if isinstance(error, Cancelled):
            self.cancelled.emit(task.message)
        elif error is not None:
            self.failed.emit(f'{title} failed', str(error) or type(error).__name__)
        elif task.generation == self.generation and not task.context.isCancelled():
            try:
                task.apply(result)
            except Exception as exception:
                traceback.print_exc()
                self.failed.emit(f'{title} failed', str(exception) or type(exception).__name__)

        self.finished.emit()
        if self.pending:
            self._startNext()
        else:
            self.busyChanged.emit(False)

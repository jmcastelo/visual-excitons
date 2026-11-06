"""
Parameters kept between sessions.

Each panel registers the values worth keeping, in one of two scopes:

- GLOBAL: preferences of the user (display, view, layout), kept in the
  application settings.
- DATASET: parameters that only make sense for one system (energy range,
  exciton, fixed particle position, supercell...), kept with each dataset in
  the list of recent datasets.

Values are restored by setting the widgets themselves, so they go through the
same code as a user's edit and everything that depends on them follows. They
are restored in the order they were registered, which matters when a widget
depends on another (e.g. the view presets on the view basis). All values are
stored as JSON.
"""

import base64

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QSplitter

GLOBAL = 'global'
DATASET = 'dataset'


def _widgetAccessors(widget):
    """Getter and setter of the value of a widget."""
    from .inspector import ValueSlider, CollapsibleSection

    if isinstance(widget, QCheckBox):
        return widget.isChecked, lambda value: widget.setChecked(bool(value))
    if isinstance(widget, QComboBox):
        # By text: robust to items being reordered or added
        def setText(value):
            if widget.findText(str(value)) >= 0:
                widget.setCurrentText(str(value))
        return widget.currentText, setText
    if isinstance(widget, QSpinBox):
        return widget.value, lambda value: widget.setValue(int(value))
    if isinstance(widget, QDoubleSpinBox):
        return widget.value, lambda value: widget.setValue(float(value))
    if isinstance(widget, QLineEdit):
        return widget.text, lambda value: widget.setText(str(value))
    if isinstance(widget, ValueSlider):
        return widget.slider.value, lambda value: widget.slider.setValue(int(value))
    if isinstance(widget, CollapsibleSection):
        return widget.isExpanded, lambda value: widget.setExpanded(bool(value))
    if isinstance(widget, QSplitter):
        return (lambda: base64.b64encode(bytes(widget.saveState())).decode('ascii'),
                lambda value: widget.restoreState(QByteArray(base64.b64decode(value))))
    raise TypeError(f'Cannot keep the state of a {type(widget).__name__}')


class PersistentState:
    """Named values of one panel, with how to read and set them."""

    def __init__(self):
        self.entries = []        # (scope, key, getter, setter)
        self.afterRestore = []   # callables run after restoring a scope: (scope) -> None

    def remember(self, key, widget=None, scope=GLOBAL, get=None, set=None):
        """Keep `widget`'s value, or the value read by `get` and set by `set`, under `key`."""
        if widget is not None:
            get, set = _widgetAccessors(widget)
        self.entries.append((scope, key, get, set))

    def values(self, scope):
        return {key: get() for s, key, get, set in self.entries if s == scope}

    def restore(self, scope, values):
        """Set the values present in `values`; unknown keys and invalid values are ignored."""
        for s, key, get, set in self.entries:
            if s == scope and key in values:
                try:
                    set(values[key])
                except (TypeError, ValueError):
                    pass
        for hook in self.afterRestore:
            hook(scope)


class StateRegistry:
    """The PersistentStates of all panels, each under a prefix."""

    def __init__(self):
        self.states = []  # (prefix, PersistentState)

    def add(self, prefix, state):
        self.states.append((prefix, state))

    def values(self, scope):
        return {f'{prefix}/{key}': value for prefix, state in self.states for key, value in state.values(scope).items()}

    def restore(self, scope, values):
        if not isinstance(values, dict):
            return
        for prefix, state in self.states:
            start = prefix + '/'
            state.restore(scope, {key[len(start):]: value for key, value in values.items() if key.startswith(start)})

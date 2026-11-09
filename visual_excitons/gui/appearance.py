"""
The Appearance of the 2D plots (the three styles), kept between sessions and
in session files.

Colors that were the theme's defaults when saved follow the current theme: a
style saved on the dark theme, with light grey axes, would otherwise be
restored as light grey axes on a white background.
"""

from PySide6.QtGui import QColor

from .theme import PLOT_COLORS

STYLE_KEYS = ('dispersion', 'absorption', 'bands')


def colorKey(color) -> str:
    return QColor(color).name(QColor.NameFormat.HexArgb)


def themeColors(dark: bool):
    """{color: role} of the default plot colors of a theme (black: the initial default foreground)."""
    colors = PLOT_COLORS[dark]
    return {colorKey(colors['foreground']): 'foreground', colorKey(QColor('black')): 'foreground',
            colorKey(colors['background']): 'background'}


def recolor(value, mapping):
    """`value` (nested dicts and lists) with the colors in `mapping` replaced."""
    if isinstance(value, dict):
        return {key: recolor(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [recolor(item, mapping) for item in value]
    if isinstance(value, str) and value in mapping:
        return mapping[value]
    return value


def appearanceState(styles, dark: bool) -> dict:
    """The three styles (dispersion, absorption, band structure) and the theme they were made on."""
    return {'dark': bool(dark), **{key: style.state() for key, style in zip(STYLE_KEYS, styles)}}


def restoreAppearance(styles, state, dark: bool, curves=False):
    """
    Set the three styles from appearanceState(); the style of each curve too if
    `curves` (and their number matches). Theme default colors are mapped to
    those of the current theme.
    """
    if not isinstance(state, dict):
        return
    saved = themeColors(bool(state.get('dark', False)))
    current = PLOT_COLORS[dark]
    mapping = {color: colorKey(current[role]) for color, role in saved.items()}
    for key, style in zip(STYLE_KEYS, styles):
        if isinstance(state.get(key), dict):
            style.setState(recolor(state[key], mapping), curves)

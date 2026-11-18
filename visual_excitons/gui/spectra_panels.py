"""
The spectra: the dispersion, absorption and band structure plots and their
controls, each shown in its own dock by the main window.
"""

import numpy as np
from PySide6.QtCore import QObject, Slot, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtGui import QColor

from .dispersion_plot import DispersionPlot
from .band_structure_plot import BandStructurePlot
from .absorption_plot import AbsorptionPlot
from .spectra_controls import SpectraControls
from .theme import PLOT_COLORS
from .inspector import NoteLabel


class SpectraPanels(QObject):
    def __init__(self, dataset, parameters, calculations, dispersionStyle, absorptionStyle, bandStructureStyle, parent=None):
        super().__init__(parent)

        self.calculations = calculations
        self.styles = (dispersionStyle, absorptionStyle, bandStructureStyle)
        # Default color of the curves: black (the light theme's foreground)
        self.foreground = PLOT_COLORS[False]['foreground']

        # Dispersion plot

        dispersionPlot = DispersionPlot(dispersionStyle)

        calculations.dispersionQPointCountChanged.connect(dispersionPlot.setSingleQPoint)

        calculations.qPathReady.connect(dispersionPlot.setXAxis)
        calculations.excitonDispersionRange.connect(dispersionPlot.setXYRange)
        calculations.excitonDispersionReady.connect(dispersionPlot.plotData)

        dispersionPlot.qPointSelected.connect(calculations.computeQPointAbsorptionSpectrum)
        dispersionPlot.qPointSelected.connect(calculations.getExcitonBandStructure)
        dispersionPlot.qPointSelected.connect(calculations.selectDispersionExciton)
        dispersionPlot.curveClicked.connect(dispersionStyle.setCurrentCurveIndex)

        # Band structure plot

        bandStructurePlot = BandStructurePlot(bandStructureStyle)

        calculations.qPathReady.connect(bandStructurePlot.setXAxis)
        calculations.excitonBandStructureReady.connect(bandStructurePlot.plotData)
        calculations.excitonBandStructureClear.connect(bandStructurePlot.clearData)
        # Its title says the Q-point, its tooltip how to read it
        calculations.excitonBandStructureReady.connect(self.updateBandStructureTitle)
        calculations.excitonBandStructureClear.connect(self.updateBandStructureTitle)

        bandStructurePlot.curveClicked.connect(bandStructureStyle.setCurrentCurveIndex)

        bandStructureStyle.weightFactorChanged.connect(calculations.setWeightFactor)

        # Absorption plot

        absorptionPlot = AbsorptionPlot(absorptionStyle)

        calculations.excitonAbsorptionReady.connect(absorptionPlot.plotData)
        calculations.excitonAbsorptionClear.connect(absorptionPlot.clearData)

        absorptionPlot.excitonsSelected.connect(calculations.getExcitonBandStructure)
        absorptionPlot.excitonsSelected.connect(calculations.selectExciton)
        absorptionPlot.curveClicked.connect(absorptionStyle.setCurrentCurveIndex)

        absorptionStyle.legendStyle.textColorChanged.connect(absorptionPlot.setLegendTextColor)
        absorptionStyle.legendStyle.textSizeChanged.connect(absorptionPlot.setLegendTextSize)
        absorptionStyle.legendStyle.backgroundColorChanged.connect(absorptionPlot.setLegendBackgroundColor)
        absorptionStyle.legendStyle.borderPenChanged.connect(absorptionPlot.setLegendBorderPen)
        absorptionStyle.legendStyle.offsetChanged.connect(absorptionPlot.setLegendOffset)

        # Spectra controls

        self.controls = SpectraControls(dataset, parameters, calculations)
        self.controls.calculateDispersionButton.clicked.connect(calculations.getExcitonDispersion)
        self.controls.showLabelsCheckBox.toggled.connect(calculations.toggleExcitonLabelsVisibility)

        # Ring around the selected exciton, kept when the plots are redrawn
        # (connected after the plots, so it is placed on the new data)
        self.dispersionPlot = dispersionPlot
        self.absorptionPlot = absorptionPlot
        self.bandStructurePlot = bandStructurePlot
        # Its panel: the plot, with a note below saying what it shows and how to read it
        self.bandStructureNote = NoteLabel()
        self.bandStructureNote.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.bandStructureNote.setContentsMargins(6, 2, 6, 4)
        self.bandStructureNote.hide()
        self.bandStructurePanel = QWidget()
        layout = QVBoxLayout(self.bandStructurePanel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bandStructurePlot, 1)
        layout.addWidget(self.bandStructureNote)
        for signal in (calculations.excitonSelected, calculations.excitonDispersionReady,
                       calculations.excitonAbsorptionReady, calculations.excitonAbsorptionClear):
            signal.connect(self.updateHighlights)
        self.controls.absorptionParametersChanged.connect(calculations.recomputeAbsorptionSpectra)

    @Slot()
    def updateBandStructureTitle(self, *args):
        """The band structure's title (its Q-point) and the note below it (how to read it)."""
        from visual_excitons.gui.composition_panel import fraction
        info = self.calculations.bandStructureInfo if len(self.calculations.k) else None
        widget = self.bandStructurePlot
        if not info:
            widget.setQPointTitle('')
            self.bandStructureNote.hide()
            return
        q = np.asarray(info['redQPoint'], dtype=float)
        gamma = np.allclose(q - np.round(q), 0.0, atol=1e-6)
        where = 'Γ' if gamma else '(' + ', '.join(fraction(x) for x in q) + ')'
        states = info['states']
        names = (f'{states[0]}–{states[-1]}' if len(states) > 1 and states == list(range(states[0], states[-1] + 1))
                 else ', '.join(map(str, states)))
        lines = [f'<b>Exciton{"s" if len(states) > 1 else ""} {names}</b> at Q{info["qIndex"] + 1} = {where}'
                 + (', with the degenerate states' if info['degenerate'] and states != info['clicked'] else '')
                 + ('; QP energies' if info.get('gw') else '; DFT energies')
                 + '. The width of each band is the weight of the exciton on it.']
        if not gamma:
            lines.append('At finite Q the hole is at k−Q: on the valence bands, the weight of the hole at k '
                         '(transitions to the electron at k+Q); on the conduction bands, that of the electron at k.')
        if info.get('energyInterpolation') == 'spline':
            lines.append('Energies interpolated with a spline on the full k-point grid: the SKW fit with symmetries '
                         'did not reproduce them for this grid.')
        if info.get('estimatedBands'):
            bands = info['estimatedBands']
            lines.append(f'QP energies of band{"s" if len(bands) > 1 else ""} ' + ', '.join(map(str, bands))
                         + ' (outside the QP database): DFT, corrected as the nearest band of the database.')
        widget.setQPointTitle(f'at Q{info["qIndex"] + 1} = {where}')
        self.bandStructureNote.setText('<br>'.join(lines))
        self.bandStructureNote.show()

    @Slot()
    def updateHighlights(self, *args):
        positions = self.calculations.selectedExcitonPositions()
        self.dispersionPlot.setHighlight(positions['dispersion'])
        self.absorptionPlot.setHighlight(positions['absorption'])

    def clearQPath(self):
        """No Q-path on the axes (no dataset)."""
        for widget in (self.dispersionPlot, self.bandStructurePlot):
            widget.getAxis('bottom').setTicks(None)

    @Slot(bool)
    def setDarkTheme(self, dark: bool):
        """Plot colors for a dark or light theme (they can still be changed under Appearance)."""
        colors = PLOT_COLORS[dark]
        foreground, background = colors['foreground'], colors['background']
        for style in self.styles:
            axes = style.axesStyle
            for color in (axes.titleColor, axes.labelsColor, axes.ticksColor, axes.axesColor):
                color.setColor(foreground)
            axes.backgroundColor.setColor(background)
        self.styles[1].legendStyle.setTextColor(foreground)
        # Curves still in the default color follow the theme
        for style in self.styles:
            style.curveStyle.replaceColor(QColor('black'), foreground)
            style.curveStyle.replaceColor(self.foreground, foreground)
        self.foreground = foreground
        # Replot, for the items drawn in the foreground color
        if self.calculations.dispPoints:
            self.calculations.emitExcitonDispersionReady()
        if self.calculations.excAbsData:
            self.calculations.emitExcitonAbsorption()

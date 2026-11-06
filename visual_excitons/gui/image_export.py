"""
Export of the 3D view as an image, at any size: the scene rendered off screen,
with the axes gizmo and the cell parameters drawn over it as on screen, scaled
with the image.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QSettings, Slot
from PySide6.QtGui import QImage, QPainter, QColor, QMatrix4x4, QVector3D
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QComboBox, QCheckBox, QHBoxLayout,
                               QLabel, QVBoxLayout)

from .axes_3d_widget import AxisGizmo
from .inspector import NoteLabel

IMAGE_FILTERS = 'PNG image (*.png);;JPEG image (*.jpg *.jpeg);;TIFF image (*.tif *.tiff)'
# Formats that cannot be transparent: the background is filled in
OPAQUE_SUFFIXES = {'.jpg', '.jpeg', '.bmp'}


def gizmoImage(view, scale):
    """
    The axes gizmo of `view` at `scale` times its size, on a transparent
    background, with its labels painted by Qt: drawn by OpenGL on a transparent
    image, text gets dark fringes.
    """
    gizmo = view.gizmo
    copy = AxisGizmo(view, size=max(1, round(gizmo.width() * scale)), labelScale=scale)
    copy.showCartesian, copy.showLattice = gizmo.showCartesian, gizmo.showLattice
    copy.showReciprocal, copy.darkTheme = gizmo.showReciprocal, gizmo.darkTheme
    copy.showLabels = False
    if gizmo.lattice is not None:
        copy.setLatticeVectors(gizmo.lattice)
    copy.rebuild()
    copy.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    copy.show()
    copy.sync()
    image = copy.grabFramebuffer().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    if gizmo.showLabels:
        # Where each label is: its 3D position projected as GLTextItem does
        rect = QRectF(copy.rect())
        viewport = (0, 0, copy.width(), copy.height())
        toScreen = QMatrix4x4()
        toScreen.viewport(rect.left(), rect.bottom(), rect.width(), -rect.height())
        toScreen = toScreen * copy.projectionMatrix(viewport, viewport) * copy.viewMatrix()
        imageScale = image.width() / max(copy.width(), 1)

        painter = QPainter(image)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        painter.scale(imageScale, imageScale)
        for item in copy.labelItems:
            point = item.align_text(toScreen.map(QVector3D(*item.pos)).toPointF())
            painter.setPen(QColor(*item.color) if isinstance(item.color, tuple) else QColor(item.color))
            painter.setFont(item.font)
            painter.drawText(point, item.text)
        painter.end()

    copy.close()
    copy.deleteLater()
    return image


def composeImage(view, width, height, transparent=False, gizmo=True, cellInfo=True):
    """The 3D view as a `width` x `height` image, with its overlays if requested (and shown)."""
    image = view.renderImage(width, height, transparent).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    scale = height / max(view.height(), 1)

    overlay = gizmoImage(view, scale) if gizmo and view.gizmo is not None and view.gizmo.isVisible() else None

    painter = QPainter(image)
    try:
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                               | QPainter.RenderHint.SmoothPixmapTransform)
        if overlay is not None:
            margin = view.gizmo.margin * scale
            painter.drawImage(QPointF(margin, height - overlay.height() - margin), overlay)
        if cellInfo and view.cellInfoLabel.isVisible():
            label = view.cellInfoLabel
            painter.translate(label.x() * scale, label.y() * scale)
            painter.scale(scale, scale)
            label.render(painter, QPoint(0, 0))   # vector text: sharp at any scale
    finally:
        painter.end()
    return image


def saveImage(image, filename, background):
    """Save `image`; formats without transparency get `background` filled in."""
    if Path(filename).suffix.lower() in OPAQUE_SUFFIXES:
        opaque = QImage(image.size(), QImage.Format.Format_RGB32)
        opaque.fill(background)
        painter = QPainter(opaque)
        painter.drawImage(0, 0, image)
        painter.end()
        image = opaque
    if not image.save(str(filename)):
        raise OSError(f'Could not write {filename}')


class ImageExportDialog(QDialog):
    """Size and contents of the exported image; the proportions of the view are kept."""

    SCALES = [1, 2, 3, 4]

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export image')
        self.view = view
        self.settings = QSettings('VisualExcitons', 'VisualExcitons')
        self.aspect = view.height() / max(view.width(), 1)

        self.scaleComboBox = QComboBox()
        self.scaleComboBox.addItems([f'{s}× the view' for s in self.SCALES] + ['Custom'])
        self.widthSpinBox = QSpinBox(minimum=16, maximum=16384, suffix=' px')
        self.heightSpinBox = QSpinBox(minimum=16, maximum=16384, suffix=' px')
        self.heightSpinBox.setEnabled(False)  # follows the width
        self.heightSpinBox.setToolTip('Follows the width: the image has the proportions of the view')

        sizeLayout = QHBoxLayout()
        sizeLayout.addWidget(self.widthSpinBox)
        sizeLayout.addWidget(QLabel('×'))
        sizeLayout.addWidget(self.heightSpinBox)
        sizeLayout.addStretch(1)

        self.transparentCheckBox = QCheckBox('Transparent background (PNG, TIFF)')
        self.gizmoCheckBox = QCheckBox('Axes')
        self.cellInfoCheckBox = QCheckBox('Cell parameters')
        self.gizmoCheckBox.setEnabled(view.gizmo is not None and view.gizmo.isVisible())
        self.cellInfoCheckBox.setEnabled(view.cellInfoLabel.isVisible())

        overlays = QHBoxLayout()
        overlays.addWidget(self.gizmoCheckBox)
        overlays.addWidget(self.cellInfoCheckBox)
        overlays.addStretch(1)

        form = QFormLayout()
        form.addRow('Size:', self.scaleComboBox)
        form.addRow('', sizeLayout)
        form.addRow('Include:', overlays)
        form.addRow('', self.transparentCheckBox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(NoteLabel('The image shows what the 3D view shows, at higher resolution: '
                                   'lines and labels are scaled with it.'))
        layout.addWidget(buttons)

        self.scaleComboBox.currentIndexChanged.connect(self.onScaleChanged)
        self.widthSpinBox.valueChanged.connect(self.onWidthChanged)

        # Last choices
        self.scaleComboBox.setCurrentIndex(int(self.settings.value('imageExport/scale', 1)))
        self.onScaleChanged(self.scaleComboBox.currentIndex())
        if self.isCustom():
            self.widthSpinBox.setValue(int(self.settings.value('imageExport/width', 2 * view.width())))
        self.transparentCheckBox.setChecked(self.settings.value('imageExport/transparent', False, type=bool))
        self.gizmoCheckBox.setChecked(self.settings.value('imageExport/gizmo', True, type=bool))
        self.cellInfoCheckBox.setChecked(self.settings.value('imageExport/cellInfo', False, type=bool))

    def isCustom(self):
        return self.scaleComboBox.currentIndex() >= len(self.SCALES)

    @Slot(int)
    def onScaleChanged(self, index):
        self.widthSpinBox.setEnabled(self.isCustom())
        if not self.isCustom():
            self.widthSpinBox.setValue(self.SCALES[index] * self.view.width())
        self.onWidthChanged(self.widthSpinBox.value())

    @Slot(int)
    def onWidthChanged(self, width):
        self.heightSpinBox.setValue(max(16, round(width * self.aspect)))

    def imageSize(self):
        return self.widthSpinBox.value(), self.heightSpinBox.value()

    def accept(self):
        self.settings.setValue('imageExport/scale', self.scaleComboBox.currentIndex())
        self.settings.setValue('imageExport/width', self.widthSpinBox.value())
        self.settings.setValue('imageExport/transparent', self.transparentCheckBox.isChecked())
        self.settings.setValue('imageExport/gizmo', self.gizmoCheckBox.isChecked())
        self.settings.setValue('imageExport/cellInfo', self.cellInfoCheckBox.isChecked())
        super().accept()

    def composedImage(self):
        width, height = self.imageSize()
        return composeImage(self.view, width, height, self.transparentCheckBox.isChecked(),
                            self.gizmoCheckBox.isChecked() and self.gizmoCheckBox.isEnabled(),
                            self.cellInfoCheckBox.isChecked() and self.cellInfoCheckBox.isEnabled())

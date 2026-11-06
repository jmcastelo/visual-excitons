"""
Checks of the image export that need OpenGL, run on the display by
test_export.py in a separate process (python tests/render_checks.py).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication(sys.argv)

import pyqtgraph as pg
from visual_excitons.gui.exciton_wf_widget import ExcitonWfWidget
from visual_excitons.gui.axes_3d_widget import AxisGizmo
from visual_excitons.gui.image_export import composeImage, saveImage

LATTICE = np.array([[4.0, 0.0, 0.0], [1.0, 5.0, 0.0], [0.0, 0.5, 6.0]])
POSITIONS = np.array([[0.0, 0.0, 0.0], [1.0, 1.5, 2.0]])


def array(image, premultiplied=False):
    """Pixels as RGBA; premultiplied (color scaled by alpha) or straight."""
    image = image.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied if premultiplied
                                  else QImage.Format.Format_RGBA8888)
    return np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.width(), 4).copy()


view = ExcitonWfWidget()
view.attach_gizmo(AxisGizmo(target=view, size=120), 10)
view.resize(320, 240)
view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
view.show()
app.processEvents()
view.plotUnitCellAtoms([83, 53], POSITIONS, np.zeros(3))
view.plotUnitCellBoundaries(LATTICE, np.zeros(3))
# Default orthographic framing (about 44 Bohr across), centered on the cell
view.setCameraParams(center=pg.Vector(2.5, 2.75, 3))
view.cellLattice = LATTICE
view.updateCellInfo()
app.processEvents()

# Any size, opaque: atom labels and antialiased edges do not make it translucent
image = array(view.renderImage(960, 720))
assert image.shape == (720, 960, 4), image.shape
assert image[..., 3].min() == 255, 'opaque render has translucent pixels'
assert (image[..., :3].sum(-1) < 600).any(), 'nothing drawn'

# Transparent: valid premultiplied alpha (no color brighter than its alpha)
transparent = array(view.renderImage(640, 480, transparent=True), premultiplied=True)
assert transparent[0, 0, 3] == 0 and transparent[..., 3].max() == 255
assert np.all(transparent[..., :3].max(-1) <= transparent[..., 3]), 'invalid premultiplied alpha'
assert view.opts['bgcolor'][3] == 1.0 and view.latticeBoundaryItems[0].width == 1.0, 'view not restored'

# With the overlays: no overflowed (black) pixels where the gizmo is composited
composed = array(composeImage(view, 640, 480, transparent=False, gizmo=True, cellInfo=True))
assert composed[..., 3].min() == 255
corner = composed[480 - 2 * 130:, :2 * 130]
assert not (corner[..., :3].sum(-1) < 30).any(), 'black pixels around the gizmo'
assert (corner[..., :3].sum(-1) < 600).any(), 'gizmo missing'

with tempfile.TemporaryDirectory() as folder:
    saveImage(composeImage(view, 640, 480), Path(folder) / 'view.jpg', QColor('white'))
    saveImage(composeImage(view, 640, 480, transparent=True), Path(folder) / 'view.png', QColor('white'))
    assert QImage(str(Path(folder) / 'view.jpg')).width() == 640
    assert QImage(str(Path(folder) / 'view.png')).hasAlphaChannel()

print('all render checks passed')

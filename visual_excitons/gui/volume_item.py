import numpy as np
import pyqtgraph.opengl as gl
from OpenGL import GL
from PySide6.QtGui import QOpenGLContext


def volumeRGBA(density, colormap, opacity, contrast, sliceDensity):
    """
    RGBA float32 volume for a density normalized to [0, 1].

    Color follows the density through `colormap`, as for the isosurfaces.

    Opacity treats the density as an absorbing medium (Beer-Lambert law), with
    `contrast` applied as a power (values > 1 fade low densities, < 1 bring them
    out). `opacity` is the opacity along the densest line of sight through the
    grid (the grid row with the largest summed absorption), so it means the same
    for any shape or extent of the density. The volume is drawn as `sliceDensity`
    slices per voxel, each blended once, so the alpha of each slice is corrected
    for their number: the result depends neither on the slice density nor on the
    grid resolution.
    """
    density = np.clip(np.asarray(density, dtype=np.float32), 0.0, 1.0)
    absorption = density ** np.float32(contrast)

    rgba = np.empty(density.shape + (4,), dtype=np.float32)
    rgba[..., :3] = colormap.mapToFloat(density)[..., :3]

    # Largest absorption summed along a grid row, over the three axes
    densestRay = max(float(absorption.sum(axis=axis).max()) for axis in range(3))
    if densestRay <= 0.0:
        rgba[..., 3] = 0.0
        return rgba

    # Per slice: 1 - (1 - opacity) ** (absorption / (sliceDensity * densestRay)),
    # computed with log1p/expm1 to stay accurate for tiny values
    opacity = min(float(opacity), 0.999)
    rgba[..., 3] = -np.expm1(absorption * np.float32(np.log1p(-opacity) / (sliceDensity * densestRay)))
    return rgba


class FloatVolumeItem(gl.GLVolumeItem):
    """
    GLVolumeItem with a half-float texture instead of an 8-bit one.

    With many slices, each slice must be very faint for the volume as a whole
    to stay translucent: alphas of 1e-3 or less, which 8 bits (steps of 1/255)
    would round to zero or to visible bands. Takes RGBA float data in [0, 1].
    """

    def _uploadData(self):
        if self.texture is None:
            self.texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_3D, self.texture)
        filt = GL.GL_LINEAR if self.smooth else GL.GL_NEAREST
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MIN_FILTER, filt)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MAG_FILTER, filt)
        for wrap in (GL.GL_TEXTURE_WRAP_S, GL.GL_TEXTURE_WRAP_T, GL.GL_TEXTURE_WRAP_R):
            GL.glTexParameteri(GL.GL_TEXTURE_3D, wrap, GL.GL_CLAMP_TO_BORDER)
        shape = self.data.shape

        if not QOpenGLContext.currentContext().isOpenGLES():
            GL.glTexImage3D(GL.GL_PROXY_TEXTURE_3D, 0, GL.GL_RGBA16F, shape[0], shape[1], shape[2], 0, GL.GL_RGBA, GL.GL_FLOAT, None)
            if GL.glGetTexLevelParameteriv(GL.GL_PROXY_TEXTURE_3D, 0, GL.GL_TEXTURE_WIDTH) == 0:
                raise Exception("OpenGL failed to create 3D texture (%dx%dx%d); too large for this hardware." % shape[:3])

        data = np.ascontiguousarray(self.data.transpose((2, 1, 0, 3)), dtype=np.float32)
        GL.glTexImage3D(GL.GL_TEXTURE_3D, 0, GL.GL_RGBA16F, shape[0], shape[1], shape[2], 0, GL.GL_RGBA, GL.GL_FLOAT, data)
        GL.glBindTexture(GL.GL_TEXTURE_3D, 0)

        # Slice geometry, as in GLVolumeItem
        all_vertices = []
        self.lists = {}
        for ax in [0, 1, 2]:
            for d in [-1, 1]:
                vertices = self.drawVolume(ax, d)
                self.lists[(ax, d)] = (len(all_vertices), len(vertices))
                all_vertices.extend(vertices)

        pos = np.array(all_vertices, dtype=np.float32)
        vbo = self.m_vbo_position
        if not vbo.isCreated():
            vbo.create()
        vbo.bind()
        vbo.allocate(pos, pos.nbytes)
        vbo.release()

        self._needUpload = False

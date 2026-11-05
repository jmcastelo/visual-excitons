import numpy as np
from OpenGL import GL
from OpenGL.GL import shaders
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QImage, QOpenGLContext, QPainter, QPainterPath, QPen
from PySide6.QtOpenGL import QOpenGLBuffer
from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem

from .gl_style import LABEL_STAGE


def labelImage(text, pixelSize=96, outline=10):
    """RGBA image (rows top to bottom) of white text with a dark outline, tightly cropped."""
    font = QFont()
    font.setPixelSize(pixelSize)
    font.setBold(True)

    path = QPainterPath()
    path.addText(QPointF(0, 0), font, text)
    rect = path.boundingRect().adjusted(-outline, -outline, outline, outline)
    path.translate(-rect.left(), -rect.top())

    image = QImage(int(np.ceil(rect.width())), int(np.ceil(rect.height())), QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.strokePath(path, QPen(QColor(20, 20, 20, 255), outline, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.fillPath(path, QColor(255, 255, 255, 255))
    painter.end()

    data = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
    # Copy: the array must not keep pointing to the QImage buffer, freed on return
    return data[:, :4 * image.width()].reshape(image.height(), image.width(), 4).copy()


class AtomLabelsItem(GLGraphicsItem):
    """
    Atom names drawn as labels on the surface of the atoms.

    Each label is a textured quad facing the camera, placed on the front surface
    of its atom (the sphere point closest to the camera) and sized relative to
    the atom radius. Unlike GLTextItem, which paints text over the finished
    image, the labels are regular 3D geometry: depth-tested, so anything between
    them and the camera hides them, and drawn before translucent items, which
    therefore tint them like the atoms underneath.

    Billboarding is done in the vertex shader, so camera changes cost nothing on
    the CPU. Textures are shared by all labels with the same text.
    """

    _program = None   # shared by the OpenGL widgets of a window, like pyqtgraph's own items

    heightFraction = 0.8     # label height relative to the atom radius
    maxWidthFraction = 1.6   # maximum label width relative to the atom radius
    surfaceOffset = 0.03     # extra distance in front of the surface, relative to the radius

    def __init__(self, parentItem=None):
        super().__init__()
        self.setGLOptions({
            GL.GL_DEPTH_TEST: True,
            'glDepthMask': (GL.GL_TRUE,),
            GL.GL_CULL_FACE: False,
            GL.GL_BLEND: True,
            'glBlendFunc': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA),
        })
        # After opaque items, before translucent ones
        self.setDepthValue(LABEL_STAGE)

        self.centers = []
        self.radii = []
        self.texts = []
        self._groups = {}   # text -> {'texture', 'vbo', 'count'}
        self._trash = []    # GL resources to free once a context is current
        self._dirty = False
        self.setParentItem(parentItem)

    def addLabels(self, centers, radii, texts):
        self.centers.extend(np.asarray(centers, dtype=np.float32).reshape(-1, 3))
        self.radii.extend(np.asarray(radii, dtype=np.float32).ravel())
        self.texts.extend(texts)
        self._dirty = True
        self.update()

    def clear(self):
        self.centers, self.radii, self.texts = [], [], []
        self._dirty = True
        self.update()

    def _freeGroups(self):
        self._trash.extend(self._groups.values())
        self._groups = {}

    def _emptyTrash(self):
        for group in self._trash:
            GL.glDeleteTextures([group['texture']])
            group['vbo'].destroy()
        self._trash.clear()

    def _rebuild(self):
        self._freeGroups()
        centers = np.array(self.centers, dtype=np.float32).reshape(-1, 3)
        radii = np.array(self.radii, dtype=np.float32)
        texts = np.array(self.texts, dtype=object)

        # Two triangles per label: corner signs and texture coordinates (image rows top to bottom)
        signs = np.array([[-1, -1], [1, -1], [1, 1], [-1, -1], [1, 1], [-1, 1]], dtype=np.float32)
        texCoords = np.column_stack([(signs[:, 0] + 1) / 2, (1 - signs[:, 1]) / 2]).astype(np.float32)

        for text in sorted(set(self.texts)):
            image = labelImage(text)
            height, width = image.shape[:2]
            aspect = width / height

            selection = texts == text
            r = radii[selection]
            halfHeight = np.minimum(0.5 * self.heightFraction * r, 0.5 * self.maxWidthFraction * r / aspect)
            halfSize = np.column_stack([halfHeight * aspect, halfHeight])                   # (n, 2)

            n = len(r)
            vertices = np.empty((n, 6, 8), dtype=np.float32)
            vertices[:, :, 0:3] = centers[selection][:, None, :]
            vertices[:, :, 3:5] = signs[None, :, :] * halfSize[:, None, :]
            vertices[:, :, 5] = (r * (1 + self.surfaceOffset))[:, None]
            vertices[:, :, 6:8] = texCoords[None, :, :]
            vertices = np.ascontiguousarray(vertices.reshape(-1, 8))

            texture = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
            GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, width, height, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, image)
            GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

            vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            vbo.create()
            vbo.bind()
            vbo.allocate(vertices, vertices.nbytes)
            vbo.release()

            self._groups[text] = {'texture': texture, 'vbo': vbo, 'count': len(vertices)}

        self._dirty = False

    def paint(self):
        self._emptyTrash()
        if self._dirty:
            self._rebuild()
        if not self._groups:
            return

        self.setupGLState()
        program = self.shaderProgram()
        GL.glUseProgram(program)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(program, 'u_mv'), 1, False,
                              np.array(self.modelViewMatrix().data(), dtype=np.float32))
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(program, 'u_proj'), 1, False,
                              np.array(self.projectionMatrix().data(), dtype=np.float32))
        GL.glUniform1i(GL.glGetUniformLocation(program, 'u_texture'), 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)

        stride = 8 * 4
        layout = [(0, 3, 0), (1, 2, 3), (2, 1, 5), (3, 2, 6)]   # (location, size, offset in floats)
        for group in self._groups.values():
            group['vbo'].bind()
            for location, size, offset in layout:
                GL.glVertexAttribPointer(location, size, GL.GL_FLOAT, False, stride,
                                         None if offset == 0 else GL.GLvoidp(offset * 4))
                GL.glEnableVertexAttribArray(location)
            group['vbo'].release()

            GL.glBindTexture(GL.GL_TEXTURE_2D, group['texture'])
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, group['count'])

            for location, _, _ in layout:
                GL.glDisableVertexAttribArray(location)

        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glUseProgram(0)

    @classmethod
    def shaderProgram(cls):
        if cls._program is not None:
            return cls._program

        context = QOpenGLContext.currentContext()

        fmt = context.format()
        if context.isOpenGLES():
            core = fmt.version() >= (3, 0)
            version = '#version 300 es\n' if core else ''
        else:
            core = fmt.version() >= (3, 1)
            version = '#version 140\n' if core else ''

        attribute, varyingOut, varyingIn = ('in', 'out', 'in') if core else ('attribute', 'varying', 'varying')
        vertexSource = f"""
            uniform mat4 u_mv;
            uniform mat4 u_proj;
            {attribute} vec3 a_center;
            {attribute} vec2 a_corner;
            {attribute} float a_radius;
            {attribute} vec2 a_texcoord;
            {varyingOut} vec2 v_texcoord;
            void main() {{
                // Atom center in view space, where the camera sits at the origin
                vec3 center = (u_mv * vec4(a_center, 1.0)).xyz;
                // Direction to the viewer: +z for orthographic projection (no perspective
                // division term), towards the eye at the origin for perspective projection
                vec3 toViewer = (u_proj[2][3] == 0.0) ? vec3(0.0, 0.0, 1.0) : normalize(-center);
                // Point of the atom surface closest to the viewer
                vec3 surface = center + toViewer * a_radius;
                // Quad facing the screen around that point
                gl_Position = u_proj * vec4(surface + vec3(a_corner, 0.0), 1.0);
                v_texcoord = a_texcoord;
            }}
        """
        fragmentSource = f"""
            #ifdef GL_ES
            precision mediump float;
            #endif
            uniform sampler2D u_texture;
            {varyingIn} vec2 v_texcoord;
            {'out vec4 fragColor;' if core else ''}
            void main() {{
                vec4 color = {'texture' if core else 'texture2D'}(u_texture, v_texcoord);
                // Transparent texels write no depth, so they hide nothing behind them
                if (color.a < 0.02) discard;
                {'fragColor' if core else 'gl_FragColor'} = color;
            }}
        """
        program = shaders.compileProgram(
            shaders.compileShader([version, vertexSource], GL.GL_VERTEX_SHADER),
            shaders.compileShader([version, fragmentSource], GL.GL_FRAGMENT_SHADER))
        for location, name in enumerate(['a_center', 'a_corner', 'a_radius', 'a_texcoord']):
            GL.glBindAttribLocation(program, location, name)
        GL.glLinkProgram(program)

        cls._program = program
        return program

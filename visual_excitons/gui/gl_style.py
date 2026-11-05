"""
Rendering settings shared by the 3D views: draw stages, OpenGL state, shaders
and fast sphere meshes.
"""

from functools import lru_cache

import numpy as np
import pyqtgraph.opengl as gl
from OpenGL import GL
from PySide6.QtGui import QSurfaceFormat
from pyqtgraph.opengl.shaders import ShaderProgram, VertexShader, FragmentShader


# Draw stages: pyqtgraph draws items in increasing depth value order.
# Opaque geometry first, then labels on top of it (they blend their edges over
# what is behind them), and translucent geometry last, sorted back to front.
OPAQUE_STAGE = 0
LABEL_STAGE = 0.5
TRANSLUCENT_STAGE = 1

# Opaque items: depth-tested and depth-writing, no blending.
OPAQUE_GL_OPTIONS = {
    GL.GL_DEPTH_TEST: True,
    'glDepthMask': (GL.GL_TRUE,),
    GL.GL_CULL_FACE: False,
    GL.GL_BLEND: False,
}

# Translucent items: depth-tested against opaque items, but writing no depth so
# they do not hide each other; correct when drawn back to front. Color is
# blended with alpha; the framebuffer alpha accumulates coverage.
TRANSLUCENT_GL_OPTIONS = {
    GL.GL_DEPTH_TEST: True,
    'glDepthMask': (GL.GL_FALSE,),
    GL.GL_CULL_FACE: False,
    GL.GL_BLEND: True,
    'glBlendFuncSeparate': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA),
}

# Multisample antialiasing for the 3D widgets
MSAA_SAMPLES = 4


def enableMultisampling(widget, samples=MSAA_SAMPLES):
    """Request multisampled rendering; call before the widget is first shown."""
    fmt = QSurfaceFormat(widget.format())
    fmt.setSamples(samples)
    widget.setFormat(fmt)


_vertexShader = """
    uniform mat4 u_mvp;
    uniform mat3 u_normal;
    attribute vec4 a_position;
    attribute vec3 a_normal;
    attribute vec4 a_color;
    varying vec4 v_color;
    varying vec3 v_normal;
    void main() {
        v_normal = normalize(u_normal * a_normal);
        v_color = a_color;
        gl_Position = u_mvp * a_position;
    }
"""

# Headlight from the viewer's upper right (view space), lighting both sides of
# each face, with an ambient term and a small specular highlight.
def _lighting(ambient, specular):
    return f"""
    vec3 shade(vec3 color, vec3 n) {{
        vec3 light = normalize(vec3(0.35, 0.45, 1.0));
        float diffuse = abs(dot(n, light));
        vec3 halfway = normalize(light + vec3(0.0, 0.0, 1.0));
        float highlight = pow(abs(dot(n, halfway)), 32.0);
        return min(color * ({ambient} + {1.0 - ambient} * diffuse) + vec3({specular} * highlight), vec3(1.0));
    }}
"""

# pyqtgraph's 'shaded' shader lights from behind the scene (direction (1, -1, -1)
# in view space) with 20% ambient, so surfaces facing the viewer come out dark.
headlightShader = ShaderProgram('headlight', [
    VertexShader(_vertexShader),
    FragmentShader("""
        #ifdef GL_ES
        precision mediump float;
        #endif
        varying vec4 v_color;
        varying vec3 v_normal;
    """ + _lighting(0.35, 0.25) + """
        void main() {
            gl_FragColor = vec4(shade(v_color.rgb, normalize(v_normal)), v_color.a);
        }
    """)
])

# Softer headlight shading (stacked translucent layers multiply its darkening)
# plus the opacity boost near silhouettes of pyqtgraph's
# 'balloon' shader: nested translucent surfaces keep their outlines and gain
# shape cues from the lighting.
litEdgesShader = ShaderProgram('headlightEdges', [
    VertexShader(_vertexShader),
    FragmentShader("""
        #ifdef GL_ES
        precision mediump float;
        #endif
        varying vec4 v_color;
        varying vec3 v_normal;
    """ + _lighting(0.65, 0.12) + """
        void main() {
            vec3 n = normalize(v_normal);
            float edge = pow(n.x * n.x + n.y * n.y, 5.0);
            float alpha = min(v_color.a * (1.0 + 2.0 * edge), 1.0);
            gl_FragColor = vec4(shade(v_color.rgb, n), alpha);
        }
    """)
])


class PrecomputedNormalsMeshData(gl.MeshData):
    """MeshData with given vertex normals, skipping pyqtgraph's slow per-vertex Python loop."""

    def __init__(self, vertexNormals, **kwds):
        super().__init__(**kwds)
        self._givenNormals = np.ascontiguousarray(vertexNormals, dtype=np.float32)

    def vertexNormals(self, indexed=None):
        if indexed is None:
            return self._givenNormals
        if indexed == 'faces':
            return self._givenNormals[self.faces()]
        raise Exception("Invalid indexing mode. Accepts: None, 'faces'")


@lru_cache(maxsize=4)
def unitSphere(rows=24, cols=24):
    """Vertices and faces of a unit sphere; its exact normals are the vertices themselves."""
    md = gl.MeshData.sphere(rows, cols, 1.0)
    vertices = md.vertexes().astype(np.float32)
    vertices /= np.linalg.norm(vertices, axis=1, keepdims=True)
    return vertices, md.faces().astype(np.uint32)


def spheresMeshData(centers, radii, colors, rows=24, cols=24):
    """
    One mesh with a sphere per center, radius and RGBA color, with exact smooth
    normals. Drawing many spheres as one item is far faster than one item each.
    """
    centers = np.asarray(centers, dtype=np.float32).reshape(-1, 3)
    radii = np.asarray(radii, dtype=np.float32).ravel()
    colors = np.asarray(colors, dtype=np.float32).reshape(-1, 4)
    unitVertices, unitFaces = unitSphere(rows, cols)
    nv, n = len(unitVertices), len(centers)

    vertices = (unitVertices[None, :, :] * radii[:, None, None] + centers[:, None, :]).reshape(-1, 3)
    normals = np.broadcast_to(unitVertices, (n, nv, 3)).reshape(-1, 3)
    faces = (unitFaces[None, :, :] + (np.arange(n, dtype=np.uint32) * nv)[:, None, None]).reshape(-1, 3)
    vertexColors = np.repeat(colors, nv, axis=0)

    return PrecomputedNormalsMeshData(normals, vertexes=vertices, faces=faces, vertexColors=vertexColors)

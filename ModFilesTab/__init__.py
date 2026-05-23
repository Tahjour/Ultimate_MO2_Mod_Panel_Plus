import ctypes
import enum
import logging
import os
import struct
import shutil
import subprocess
import sys
import fnmatch

# Suppress Qt font warnings on Windows
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"

from collections import Counter
from datetime import datetime
from threading import get_ident
from pathlib import Path
from typing import Optional

import mobase
from PyQt6.QtCore import (
    Qt,
    QByteArray,
    QCoreApplication,
    QItemSelectionModel,
    QModelIndex,
    QMimeData,
    QPoint,
    QRegularExpression,
    QSortFilterProxyModel,
    QSettings,
    QTimer,
    QUrl,
    QPropertyAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QDrag,
    QAction,
    QIcon,
    QImageReader,
    QMatrix4x4,
    QOpenGLContext,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
    QVector4D,
)
from PyQt6.QtWidgets import (
	QApplication,
	QDialog,
	QDialogButtonBox,
	QHBoxLayout,
	QHeaderView,
	QInputDialog,
	QLabel,
	QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
	QListWidget,
	QMenu,
	QMessageBox,
	QPushButton,
	QComboBox,
	QPlainTextEdit,
	QScrollArea,
	QSplitter,
	QStyle,
	QTabWidget,
	QTreeView,
    QAbstractItemView,
	QVBoxLayout,
	QWidget,
)

from .bsa_preview import build_bsa_preview
from .hkx_preview import build_hkx_preview
from .nif_preview import build_nif_preview
from .pex_preview import build_pex_preview

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from PyQt6.QtOpenGL import (
        QOpenGLBuffer,
        QOpenGLDebugLogger,
        QOpenGLShader,
        QOpenGLShaderProgram,
        QOpenGLTexture,
        QOpenGLVersionProfile,
        QOpenGLVertexArrayObject,
        QOpenGLVersionFunctionsFactory,
    )
    _DDS_GL_AVAILABLE = True
except Exception:
    QOpenGLWidget = None
    QOpenGLBuffer = None
    QOpenGLDebugLogger = None
    QOpenGLShader = None
    QOpenGLShaderProgram = None
    QOpenGLTexture = None
    QOpenGLVersionProfile = None
    QOpenGLVertexArrayObject = None
    QOpenGLVersionFunctionsFactory = None
    _DDS_GL_AVAILABLE = False

_TAB_LABEL = "File Explorer"

# Кастомные роли хранятся на элементах столбца 0
_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 1
_ROLE_SIZE = Qt.ItemDataRole.UserRole + 2

DDSWidget = None
DDSOptions = None
ColourChannels = None
DDSChannelManager = None
DDSFile = None
_DDS_PREVIEW_AVAILABLE = False
_DDS_PREVIEW_ERROR: Optional[str] = None
_DDS_MODULES_LOADED = False

_LOG_ENABLED = True


def _log(tag: str, message: str) -> None:
    if not _LOG_ENABLED:
        return
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[ModFilesTab {ts} {tag} t{get_ident()}] {message}")


def _load_dds_modules() -> bool:
    global DDSWidget
    global DDSOptions
    global ColourChannels
    global DDSChannelManager
    global DDSFile
    global _DDS_PREVIEW_AVAILABLE
    global _DDS_PREVIEW_ERROR
    global _DDS_MODULES_LOADED

    if _DDS_MODULES_LOADED:
        return _DDS_PREVIEW_AVAILABLE

    _DDS_MODULES_LOADED = True
    try:
        if not _DDS_GL_AVAILABLE:
            _DDS_PREVIEW_AVAILABLE = False
            _DDS_PREVIEW_ERROR = "OpenGL widgets not available"
            return False

        data_dir = Path(__file__).resolve().parents[1] / "data"
        if data_dir.is_dir():
            data_str = str(data_dir)
            if data_str not in sys.path:
                sys.path.append(data_str)

        from DDS.DDSFile import DDSFile as _DDSFile

        DDSFile = _DDSFile
        _DDS_PREVIEW_AVAILABLE = True
        _DDS_PREVIEW_ERROR = None
    except Exception as exc:
        _DDS_PREVIEW_AVAILABLE = False
        _DDS_PREVIEW_ERROR = str(exc)

    return _DDS_PREVIEW_AVAILABLE


if _DDS_GL_AVAILABLE:
    vertexShader2D = """
#version 150

uniform float aspectRatioRatio;
uniform mat4 viewMatrix;

in vec4 position;
in vec2 texCoordIn;

out vec2 texCoord;

void main()
{
    texCoord = texCoordIn;
    gl_Position = viewMatrix * position;
    if (aspectRatioRatio >= 1.0)
        gl_Position.y /= aspectRatioRatio;
    else
        gl_Position.x *= aspectRatioRatio;
}
"""

    vertexShaderCube = """
#version 150

uniform float aspectRatioRatio;
uniform mat4 viewMatrix;

in vec4 position;
in vec2 texCoordIn;

out vec2 texCoord;

void main()
{
    texCoord = texCoordIn;
    gl_Position = viewMatrix * position;
    if (aspectRatioRatio >= 1.0)
        gl_Position.y /= aspectRatioRatio;
    else
        gl_Position.x *= aspectRatioRatio;
}
"""

    fragmentShaderFloat = """
#version 150

uniform sampler2D aTexture;
uniform mat4 channelMatrix;
uniform vec4 channelOffset;

in vec2 texCoord;

void main()
{
    gl_FragData[0] = channelMatrix * texture(aTexture, texCoord) + channelOffset;
}
"""

    fragmentShaderUInt = """
#version 150

uniform usampler2D aTexture;
uniform mat4 channelMatrix;
uniform vec4 channelOffset;

in vec2 texCoord;

void main()
{
    gl_FragData[0] = channelMatrix * texture(aTexture, texCoord) + channelOffset;
}
"""

    fragmentShaderSInt = """
#version 150

uniform isampler2D aTexture;
uniform mat4 channelMatrix;
uniform vec4 channelOffset;

in vec2 texCoord;

void main()
{
    gl_FragData[0] = channelMatrix * texture(aTexture, texCoord) + channelOffset;
}
"""

    fragmentShaderCube = """
#version 150

uniform samplerCube aTexture;
uniform mat4 channelMatrix;
uniform vec4 channelOffset;

in vec2 texCoord;

const float PI = 3.1415926535897932384626433832795;

void main()
{
    float theta = -2.0 * PI * texCoord.x;
    float phi   = PI * texCoord.y;
    gl_FragData[0] = channelMatrix *
        texture(aTexture, vec3(sin(theta) * sin(phi),
                               cos(theta) * sin(phi),
                               cos(phi))) + channelOffset;
}
"""

    transparencyVS = """
#version 150

in vec4 position;

void main()
{
    gl_Position = position;
}
"""

    transparencyFS = """
#version 150

uniform vec4 backgroundColour;

void main()
{
    float x = gl_FragCoord.x;
    float y = gl_FragCoord.y;
    x = mod(x, 16.0);
    y = mod(y, 16.0);

    gl_FragData[0] = x < 8.0 ^^ y < 8.0
       ? vec4(vec3(191.0/255.0), 1.0)
       : vec4(1.0);

    gl_FragData[0].rgb = backgroundColour.rgb * backgroundColour.a +
                         gl_FragData[0].rgb * (1.0 - backgroundColour.a);
}
"""

    vertices = [
        -1.0, -1.0,  0.5, 1.0,    0.0, 1.0,
        -1.0,  1.0,  0.5, 1.0,    0.0, 0.0,
         1.0,  1.0,  0.5, 1.0,    1.0, 0.0,

        -1.0, -1.0,  0.5, 1.0,    0.0, 1.0,
         1.0,  1.0,  0.5, 1.0,    1.0, 0.0,
         1.0, -1.0,  0.5, 1.0,    1.0, 1.0,
    ]

    glVersionProfile = QOpenGLVersionProfile()
    glVersionProfile.setVersion(2, 1)

    class DDSOptions:
        def __init__(
            self,
            colour: QColor = QColor(0, 0, 0, 0),
            channelMatrix: QMatrix4x4 = QMatrix4x4(),
            channelOffset: QVector4D = QVector4D(),
        ):
            self.backgroundColour = None
            self.channelMatrix = None
            self.channelOffset = None
            self.setBackgroundColour(colour)
            self.setChannelMatrix(channelMatrix)
            self.setChannelOffset(channelOffset)

        def setBackgroundColour(self, colour: QColor):
            if isinstance(colour, QColor) and colour.isValid():
                self.backgroundColour = colour
            else:
                raise TypeError(f"{colour} is not a valid QColor object.")

        def getBackgroundColour(self) -> QColor:
            return self.backgroundColour

        def getChannelMatrix(self) -> QMatrix4x4:
            return self.channelMatrix

        def setChannelMatrix(self, matrix):
            self.channelMatrix = QMatrix4x4(matrix)

        def getChannelOffset(self) -> QVector4D:
            return self.channelOffset

        def setChannelOffset(self, vector):
            self.channelOffset = QVector4D(vector)

    class ColourChannels(enum.Enum):
        RGBA = "Color and Alpha"
        RGB = "Color"
        A = "Alpha"
        R = "Red"
        G = "Green"
        B = "Blue"

    class DDSChannelManager:
        def __init__(self, channels: ColourChannels):
            self.channels = channels

        def setChannels(self, options: DDSOptions, channels: ColourChannels):
            self.channels = channels

            def drawColour(alpha: bool):
                colorMatrix = QMatrix4x4()
                colorOffset = QVector4D()
                if not alpha:
                    colorMatrix[3, 3] = 0
                    colorOffset.setW(1.0)
                options.setChannelMatrix(colorMatrix)
                options.setChannelOffset(colorOffset)

            def drawGrayscale(channel: ColourChannels):
                colorOffset = QVector4D(0, 0, 0, 1)
                channelVector = [0, 0, 0, 0]
                if channels == ColourChannels.R:
                    channelVector[0] = 1
                elif channels == ColourChannels.G:
                    channelVector[1] = 1
                elif channels == ColourChannels.B:
                    channelVector[2] = 1
                elif channels == ColourChannels.A:
                    channelVector[3] = 1
                else:
                    raise ValueError("channel must be a single color channel.")
                alphaVector = [0, 0, 0, 0]
                colorMatrix = channelVector * 3 + alphaVector
                options.setChannelMatrix(colorMatrix)
                options.setChannelOffset(colorOffset)

            if channels == ColourChannels.RGBA:
                drawColour(True)
            elif channels == ColourChannels.RGB:
                drawColour(False)
            else:
                drawGrayscale(channels)

    class DDSWidget(QOpenGLWidget):
        def __init__(self, ddsFile, ddsOptions, parent=None, f=Qt.WindowType(0)):
            super().__init__(parent, f)
            self.ddsFile = ddsFile
            self.ddsOptions = ddsOptions
            self.clean = True
            self.logger = None
            self.program = None
            self.transparencyProgram = None
            self.texture = None
            self.vbo = None
            self.vao = None
            self.viewMatrix = QMatrix4x4()
            self._log_id = hex(id(self))

        def initializeGL(self):
            try:
                _log("DDS", f"initializeGL start widget={self._log_id}")
                if self.logger:
                    self.logger.initialize()
                    self.logger.messageLogged.connect(
                        lambda message: qDebug(self.tr("OpenGL debug message: {0}").format(message.message())))
                    self.logger.startLogging()

                ctx = self.context()
                if ctx is not None:
                    ctx.aboutToBeDestroyed.connect(self.cleanup)
                _log("DDS", f"initializeGL ctx_valid={bool(ctx and ctx.isValid())} widget={self._log_id}")

                gl = QOpenGLVersionFunctionsFactory.get(glVersionProfile)
                if gl is None:
                    self.clean = True
                    _log("DDS", f"initializeGL no gl widget={self._log_id}")
                    return

                fragmentShader = None
                vertexShader = vertexShader2D
                if self.ddsFile.isCubemap:
                    fragmentShader = fragmentShaderCube
                    vertexShader = vertexShaderCube
                    ctx = QOpenGLContext.currentContext()
                    if ctx and ctx.hasExtension(b"GL_ARB_seamless_cube_map"):
                        GL_TEXTURE_CUBE_MAP_SEAMLESS = 0x884F
                        gl.glEnable(GL_TEXTURE_CUBE_MAP_SEAMLESS)
                elif self.ddsFile.glFormat.samplerType == "F":
                    fragmentShader = fragmentShaderFloat
                elif self.ddsFile.glFormat.samplerType == "UI":
                    fragmentShader = fragmentShaderUInt
                else:
                    fragmentShader = fragmentShaderSInt

                self.program = QOpenGLShaderProgram(self)
                if not self.program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertexShader):
                    raise RuntimeError("Failed to compile DDS vertex shader")
                if not self.program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragmentShader):
                    raise RuntimeError("Failed to compile DDS fragment shader")
                self.program.bindAttributeLocation("position", 0)
                self.program.bindAttributeLocation("texCoordIn", 1)
                if not self.program.link():
                    raise RuntimeError("Failed to link DDS shader program")

                self.transparencyProgram = QOpenGLShaderProgram(self)
                if not self.transparencyProgram.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, transparencyVS):
                    raise RuntimeError("Failed to compile transparency vertex shader")
                if not self.transparencyProgram.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, transparencyFS):
                    raise RuntimeError("Failed to compile transparency fragment shader")
                self.transparencyProgram.bindAttributeLocation("position", 0)
                if not self.transparencyProgram.link():
                    raise RuntimeError("Failed to link transparency shader program")

                self.vao = QOpenGLVertexArrayObject(self)
                binder = QOpenGLVertexArrayObject.Binder(self.vao)

                self.vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
                self.vbo.create()
                self.vbo.bind()

                theBytes = struct.pack("%sf" % len(vertices), *vertices)
                self.vbo.allocate(theBytes, len(theBytes))

                gl.glEnableVertexAttribArray(0)
                gl.glEnableVertexAttribArray(1)
                gl.glVertexAttribPointer(0, 4, gl.GL_FLOAT, False, 6 * 4, 0)
                gl.glVertexAttribPointer(1, 2, gl.GL_FLOAT, False, 6 * 4, 4 * 4)

                ctx = QOpenGLContext.currentContext()
                if not ctx or not ctx.isValid():
                    raise RuntimeError("No valid OpenGL context for DDS texture upload")
                self.texture = self.ddsFile.asQOpenGLTexture(gl, ctx)

                self.viewMatrix = QMatrix4x4()
                self.clean = False
                _log("DDS", f"initializeGL ok widget={self._log_id}")
            except Exception as e:
                print(f"DEBUG: Error in DDSWidget.initializeGL: {e}")
                _log("DDS", f"initializeGL error={e} widget={self._log_id}")
                self.program = None
                self.transparencyProgram = None
                self.texture = None
                self.vbo = None
                self.vao = None
                self.clean = True

        def resizeGL(self, w, h):
            try:
                if not self.program or not self.texture or h == 0:
                    return
                tex_h = self.texture.height()
                if tex_h == 0:
                    return
                aspectRatioTex = self.texture.width() / tex_h
                aspectRatioWidget = w / h
                ratioRatio = aspectRatioTex / aspectRatioWidget if aspectRatioWidget else 1.0

                self.program.bind()
                self.program.setUniformValue("aspectRatioRatio", ratioRatio)
                self.program.release()
                _log("DDS", f"resizeGL {w}x{h} ratio={ratioRatio:.3f} widget={self._log_id}")
            except Exception as e:
                print(f"DEBUG: Error in DDSWidget.resizeGL: {e}")
                _log("DDS", f"resizeGL error={e} widget={self._log_id}")

        def paintGL(self):
            try:
                gl = QOpenGLVersionFunctionsFactory.get(glVersionProfile)
                if gl is None or not self.program or not self.transparencyProgram or not self.vao:
                    return
                binder = QOpenGLVertexArrayObject.Binder(self.vao)

                _log("DDS", f"paintGL start widget={self._log_id}")

                gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

                self.transparencyProgram.bind()
                bgViewMatrix = QMatrix4x4()
                self.transparencyProgram.setUniformValue("viewMatrix", bgViewMatrix)
                backgroundColour = self.ddsOptions.getBackgroundColour()
                if backgroundColour and backgroundColour.isValid():
                    self.transparencyProgram.setUniformValue("backgroundColour", backgroundColour)
                gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                self.transparencyProgram.release()

                self.program.bind()
                self.program.setUniformValue("viewMatrix", self.viewMatrix)
                if self.texture:
                    self.texture.bind()

                gl.glEnable(gl.GL_BLEND)
                gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

                self.program.setUniformValue("channelMatrix", self.ddsOptions.getChannelMatrix())
                self.program.setUniformValue("channelOffset", self.ddsOptions.getChannelOffset())

                gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

                if self.texture:
                    self.texture.release()
                self.program.release()
                _log("DDS", f"paintGL end widget={self._log_id}")
            except Exception as e:
                print(f"DEBUG: Error in DDSWidget.paintGL: {e}")
                _log("DDS", f"paintGL error={e} widget={self._log_id}")

        def cleanup(self):
            if self.clean:
                return
            self.clean = True
            try:
                _log("DDS", f"cleanup start widget={self._log_id}")
                self.setVisible(False)
                ctx = self.context() or QOpenGLContext.currentContext()
                ctx_ok = ctx is not None and ctx.isValid()
                _log("DDS", f"cleanup ctx_valid={ctx_ok} widget={self._log_id}")
                if ctx_ok:
                    self.makeCurrent()
                self.program = None
                self.transparencyProgram = None
                self.texture = None
                self.vbo = None
                self.vao = None
                if ctx_ok:
                    self.doneCurrent()
                _log("DDS", f"cleanup end widget={self._log_id}")
            except Exception as e:
                print(f"DEBUG: Error during cleanup: {str(e)}")
                _log("DDS", f"cleanup error={e} widget={self._log_id}")

        def tr(self, str):
            return QCoreApplication.translate("DDSWidget", str)


# ── Утилиты ───────────────────────────────────────────────────────────


def _human_size(nbytes: int) -> str:
    """Человекочитаемый размер файла."""
    v = float(nbytes)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(v) < 1024 or u == "TB":
            return f"{v:.0f} {u}" if u == "B" else f"{v:.1f} {u}"
        v /= 1024.0
    return f"{v:.1f} PB"


def _is_subpath(child: Path, parent: Path) -> bool:
    """Проверка что child находится внутри parent (совместимо с Python 3.8+)."""
    try:
        child.absolute().relative_to(parent.absolute())
        return True
    except ValueError:
        return False


def _mod_directory(org: mobase.IOrganizer, name: str) -> Optional[Path]:
    """Определяет абсолютный путь к папке мода по имени."""
    try:
        mod = org.modList().getMod(name)
        if mod is not None:
            p = mod.absolutePath()
            if p and os.path.isdir(p):
                return Path(p)
    except Exception:
        pass
    try:
        p = os.path.join(org.modsPath(), name)
        if os.path.isdir(p):
            return Path(p)
    except Exception:
        pass
    return None


def _find_mod_list_view() -> Optional[QTreeView]:
    """Находит QTreeView списка модов MO2 по objectName."""
    for w in QApplication.allWidgets():
        if isinstance(w, QTreeView) and w.objectName() == "modList":
            return w
    return None


def _find_right_pane(window) -> Optional[QTabWidget]:
    """Находит правую панель вкладок главного окна MO2."""
    tabs = window.findChildren(QTabWidget)
    if not tabs:
        return None

    known = {"plugins", "archives", "data", "saves", "downloads"}
    for tw in tabs:
        if not tw.isVisible() or tw.count() < 2:
            continue
        labels = {tw.tabText(i).lower() for i in range(tw.count())}
        if len(labels & known) >= 2:
            return tw

    # Фоллбэк: самый правый видимый QTabWidget
    cx = window.geometry().width() // 2
    best, bx = None, -1
    for tw in tabs:
        if not tw.isVisible() or tw.count() < 2:
            continue
        x = window.mapFromGlobal(tw.mapToGlobal(tw.rect().topLeft())).x()
        if x > cx * 0.4 and x > bx:
            best, bx = tw, x
    return best


def _reveal_in_explorer(path: Path) -> None:
    """Открыть папку и выделить файл (Windows) или просто открыть каталог."""
    if sys.platform == "win32":
        try:
            subprocess.Popen(["explorer", "/select,", str(path)])
            return
        except Exception:
            pass
    target = path if path.is_dir() else path.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def _shell_execute(verb: Optional[str], path: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        res = ctypes.windll.shell32.ShellExecuteW(
            None, verb, str(path), None, None, 1
        )
        return res > 32
    except Exception:
        return False


def _show_properties(path: Path) -> bool:
    return _shell_execute("properties", path)


def _open_with_dialog(path: Path) -> bool:
    return _shell_execute("openas", path)


# ── Прокси-модель с сортировкой ───────────────────────────────────────


class _SortProxy(QSortFilterProxyModel):
    """
    Сортировка: папки всегда перед файлами.
    Столбец Size сортируется по сырому числу байт, а не по строке.
    Рекурсивная фильтрация по имени (столбец 0).
    """

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        l0 = left.sibling(left.row(), 0)
        r0 = right.sibling(right.row(), 0)
        l_dir = bool(l0.data(_ROLE_IS_DIR))
        r_dir = bool(r0.data(_ROLE_IS_DIR))

        if l_dir != r_dir:
            return l_dir if self.sortOrder() == Qt.SortOrder.AscendingOrder else r_dir

        # Размер — числовое сравнение
        if left.column() == 1:
            l_size = l0.data(_ROLE_SIZE)
            r_size = r0.data(_ROLE_SIZE)
            return (l_size if isinstance(l_size, int) else 0) < (
                r_size if isinstance(r_size, int) else 0
            )

        return super().lessThan(left, right)


# ── Дерево файлов с drag-and-drop ─────────────────────────────────────


class _FilesTree(QTreeView):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root: Optional[Path] = None
        self._press_pos: Optional[QPoint] = None
        self._owner: Optional["ModFilesWidget"] = None
        self._clipboard_base: Optional[Path] = None
        self._clipboard_rel: list[str] = []
        self._clipboard_cut = False

        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSortingEnabled(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.doubleClicked.connect(self._on_double_click)

    def set_root(self, path: Optional[Path]) -> None:
        self._root = path

    def set_owner(self, owner: "ModFilesWidget") -> None:
        self._owner = owner

    # ── Выбранные пути ──

    def _selected_paths(self) -> list[Path]:
        out: list[Path] = []
        sel = self.selectionModel()
        if sel is None:
            return out
        for idx in sel.selectedRows(0):
            p = idx.data(_ROLE_PATH)
            if isinstance(p, str) and p:
                out.append(Path(p))
        return out

    def _target_dir(self, paths: list[Path]) -> Optional[Path]:
        if paths:
            p = paths[0]
            if p.is_dir():
                return p
            return p.parent
        return self._root

    def _can_paste(self) -> bool:
        if self._clipboard_rel and self._clipboard_base:
            return True
        cb = QApplication.clipboard()
        if cb is None:
            return False
        mime = cb.mimeData()
        return bool(mime and mime.hasUrls())

    def _set_clipboard(self, paths: list[Path], cut: bool) -> None:
        if not paths:
            return
        try:
            base = Path(os.path.commonpath([str(p) for p in paths]))
        except Exception:
            base = paths[0].parent
        if base.is_file():
            base = base.parent
        rel = []
        for p in paths:
            try:
                rel.append(str(p.relative_to(base)))
            except Exception:
                rel.append(p.name)
        self._clipboard_base = base
        self._clipboard_rel = rel
        self._clipboard_cut = cut
        cb = QApplication.clipboard()
        if cb:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
            cb.setMimeData(mime)

    # ── Drag наружу ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
        else:
            self._press_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._press_pos is not None
            and (event.pos() - self._press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            try:
                paths = self._selected_paths()
            except (RuntimeError, IndexError):
                paths = []
            if paths:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.CopyAction)
            return
        super().mouseMoveEvent(event)

    # ── Drop внутрь ──

    def dragEnterEvent(self, event):
        if event.mimeData() and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData() and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self._root or not event.mimeData() or not event.mimeData().hasUrls():
            event.ignore()
            return

        pos = (
            event.position().toPoint()
            if hasattr(event, "position")
            else event.pos()
        )
        target = self._drop_target(self.indexAt(pos))
        if target is None:
            event.ignore()
            return

        errors: list[str] = []
        copied = 0
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            src = Path(url.toLocalFile())
            if not src.exists():
                continue
            # Не копировать файлы мода в себя же
            if _is_subpath(src, self._root):
                continue

            dst = target / src.name
            try:
                if src.is_dir():
                    if dst.exists():
                        errors.append(f"Already exists: {src.name}")
                        continue
                    shutil.copytree(src, dst)
                else:
                    if dst.exists():
                        ans = QMessageBox.question(
                            self,
                            "File exists",
                            f"'{src.name}' already exists in\n{target}\n\nOverwrite?",
                            QMessageBox.StandardButton.Yes
                            | QMessageBox.StandardButton.No,
                        )
                        if ans != QMessageBox.StandardButton.Yes:
                            continue
                    shutil.copy2(src, dst)
                copied += 1
            except Exception as exc:
                errors.append(f"{src.name}: {exc}")

        event.acceptProposedAction()
        if copied and self._owner:
            self._owner.refresh()
        if errors:
            QMessageBox.warning(
                self,
                "Drop errors",
                "Some items could not be copied:\n\n" + "\n".join(errors),
            )

    def _drop_target(self, proxy_idx: QModelIndex) -> Optional[Path]:
        """
        Определить целевую папку для drop.
        proxy_idx — индекс в proxy-модели, полученный из indexAt().
        Нужно маппить через proxy → source, чтобы прочитать _ROLE_PATH.
        """
        if not self._root:
            return None
        if not proxy_idx.isValid():
            return self._root

        # Маппим proxy индекс → source индекс
        proxy_model = self.model()
        if proxy_model is None:
            return self._root
        if isinstance(proxy_model, QSortFilterProxyModel):
            source_idx = proxy_model.mapToSource(proxy_idx)
        else:
            source_idx = proxy_idx

        # Берём столбец 0 source-модели
        col0 = source_idx.sibling(source_idx.row(), 0)
        p = col0.data(_ROLE_PATH)
        if not isinstance(p, str):
            return self._root
        path = Path(p)
        if path.is_dir():
            return path
        # Файл — целью является его родительская папка
        return path.parent

    # ── Клавиатура ──

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            if self._owner:
                self._owner.refresh()
            return
        if event.key() == Qt.Key.Key_Delete:
            paths = self._selected_paths()
            if paths:
                self._action_delete(paths)
            return
        if event.key() == Qt.Key.Key_F2:
            paths = self._selected_paths()
            if len(paths) == 1:
                self._action_rename(paths[0])
            return
        if (
            event.key() == Qt.Key.Key_X
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            paths = self._selected_paths()
            if paths:
                self._action_cut(paths)
            return
        if (
            event.key() == Qt.Key.Key_C
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            paths = self._selected_paths()
            if paths:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._action_copy_paths(paths)
                else:
                    self._action_copy(paths)
            return
        if (
            event.key() == Qt.Key.Key_V
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            target = self._target_dir(self._selected_paths())
            if target:
                self._action_paste(target)
            return
        super().keyPressEvent(event)

    # ── Контекстное меню ──

    def _context_menu(self, pos: QPoint) -> None:
        paths = self._selected_paths()
        menu = QMenu(self)
        target = self._target_dir(paths)
        can_paste = bool(target and self._can_paste())

        if paths:
            menu.addAction("Open / Run", lambda: self._action_open(paths))
            if len(paths) == 1 and paths[0].is_file():
                menu.addAction("Open with...", lambda: self._action_open_with(paths[0]))
            menu.addAction("Show in Explorer", lambda: _reveal_in_explorer(paths[0]))
            menu.addSeparator()
            menu.addAction("Cut  (Ctrl+X)", lambda: self._action_cut(paths))
            menu.addAction("Copy  (Ctrl+C)", lambda: self._action_copy(paths))
            if can_paste:
                menu.addAction("Paste  (Ctrl+V)", lambda: self._action_paste(target))
            if len(paths) == 1:
                menu.addAction("Rename  (F2)", lambda: self._action_rename(paths[0]))
            menu.addAction("Copy path(s)  (Ctrl+Shift+C)", lambda: self._action_copy_paths(paths))
            if len(paths) == 1:
                menu.addAction("Properties", lambda: self._action_properties(paths[0]))
            menu.addSeparator()
            if target:
                menu.addAction("New folder", lambda: self._action_new_folder(target))
                menu.addAction("New file", lambda: self._action_new_file(target))
                menu.addSeparator()
            menu.addAction("Delete  (Del)", lambda: self._action_delete(paths))
        elif self._root:
            menu.addAction(
                "Open mod folder",
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(self._root))
                ),
            )
            menu.addSeparator()
            if can_paste:
                menu.addAction("Paste  (Ctrl+V)", lambda: self._action_paste(target))
            if target:
                menu.addAction("New folder", lambda: self._action_new_folder(target))
                menu.addAction("New file", lambda: self._action_new_file(target))

        menu.addSeparator()
        menu.addAction(
            "Refresh  (F5)",
            lambda: self._owner.refresh() if self._owner else None,
        )
        menu.exec(self.viewport().mapToGlobal(pos))

    def _action_open(self, paths: list[Path]) -> None:
        for p in paths[:5]:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _action_open_with(self, path: Path) -> None:
        if not _open_with_dialog(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _action_properties(self, path: Path) -> None:
        if not _show_properties(path):
            QMessageBox.warning(self, "Properties", "Cannot open properties dialog")

    def _action_copy(self, paths: list[Path]) -> None:
        self._set_clipboard(paths, False)

    def _action_cut(self, paths: list[Path]) -> None:
        self._set_clipboard(paths, True)

    def _action_paste(self, target: Path) -> None:
        if not target.exists():
            QMessageBox.warning(self, "Paste", "Target folder does not exist")
            return
        errors: list[str] = []
        changed = False
        if self._clipboard_base and self._clipboard_rel:
            base = self._clipboard_base
            move = self._clipboard_cut
            cancelled = False
            for rel in self._clipboard_rel:
                src = base / rel
                if not src.exists():
                    errors.append(f"Missing: {rel}")
                    continue
                if src.is_dir() and _is_subpath(target, src):
                    errors.append(f"Invalid target for {src.name}")
                    continue
                dst = target / rel
                res = self._copy_item(src, dst, move)
                if res is None:
                    cancelled = True
                    break
                if res:
                    changed = True
            if move and not errors and not cancelled:
                self._clipboard_base = None
                self._clipboard_rel = []
                self._clipboard_cut = False
        else:
            cb = QApplication.clipboard()
            mime = cb.mimeData() if cb else None
            if not mime or not mime.hasUrls():
                return
            for url in mime.urls():
                if not url.isLocalFile():
                    continue
                src = Path(url.toLocalFile())
                if not src.exists():
                    continue
                if src.is_dir() and _is_subpath(target, src):
                    errors.append(f"Invalid target for {src.name}")
                    continue
                dst = target / src.name
                res = self._copy_item(src, dst, False)
                if res is None:
                    break
                if res:
                    changed = True
        if changed and self._owner:
            self._owner.refresh()
        if errors:
            QMessageBox.warning(self, "Paste", "Some items could not be pasted:\n\n" + "\n".join(errors))

    def _action_copy_paths(self, paths: list[Path]) -> None:
        cb = QApplication.clipboard()
        if cb:
            cb.setText("\n".join(str(p) for p in paths))

    def _copy_item(self, src: Path, dst: Path, move: bool) -> Optional[bool]:
        if dst.exists():
            ans = QMessageBox.question(
                self,
                "Already exists",
                f"'{dst.name}' already exists in\n{dst.parent}\n\nOverwrite?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if ans == QMessageBox.StandardButton.Cancel:
                return None
            if ans != QMessageBox.StandardButton.Yes:
                return False
            try:
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            except Exception as exc:
                QMessageBox.warning(self, "Overwrite failed", str(exc))
                return False
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if move:
                shutil.move(str(src), str(dst))
            else:
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Paste failed", f"{src.name}: {exc}")
            return False

    def _action_new_folder(self, target: Path) -> None:
        name, ok = QInputDialog.getText(self, "New folder", "Folder name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        invalid_chars = set('<>:"/\\|?*')
        if any(c in invalid_chars for c in name):
            QMessageBox.warning(self, "Invalid name", f"Name contains invalid characters: {invalid_chars}")
            return
        path = target / name
        if path.exists():
            QMessageBox.warning(self, "Error", f"'{name}' already exists in this location.")
            return
        try:
            path.mkdir(parents=True, exist_ok=False)
        except Exception as exc:
            QMessageBox.warning(self, "Create folder failed", str(exc))
            return
        if self._owner:
            self._owner.refresh()

    def _action_new_file(self, target: Path) -> None:
        name, ok = QInputDialog.getText(self, "New file", "File name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        invalid_chars = set('<>:"/\\|?*')
        if any(c in invalid_chars for c in name):
            QMessageBox.warning(self, "Invalid name", f"Name contains invalid characters: {invalid_chars}")
            return
        path = target / name
        if path.exists():
            QMessageBox.warning(self, "Error", f"'{name}' already exists in this location.")
            return
        try:
            with path.open("x"):
                pass
        except Exception as exc:
            QMessageBox.warning(self, "Create file failed", str(exc))
            return
        if self._owner:
            self._owner.refresh()

    def _action_rename(self, path: Path) -> None:
        new_name, ok = QInputDialog.getText(
            self,
            "Rename",
            f"New name for '{path.name}':",
            QLineEdit.EchoMode.Normal,
            path.name,
        )
        if not ok or not new_name or new_name == path.name:
            return
        # Проверка на недопустимые символы
        invalid_chars = set('<>:"/\\|?*')
        if any(c in invalid_chars for c in new_name):
            QMessageBox.warning(
                self,
                "Invalid name",
                f"Name contains invalid characters: {invalid_chars}",
            )
            return
        new_path = path.parent / new_name
        if new_path.exists():
            QMessageBox.warning(
                self, "Error", f"'{new_name}' already exists in this location."
            )
            return
        try:
            path.rename(new_path)
        except OSError as e:
            QMessageBox.warning(self, "Rename failed", str(e))
            return
        if self._owner:
            self._owner.refresh()

    def _action_delete(self, paths: list[Path]) -> None:
        names = "\n".join(f"  • {p.name}" for p in paths[:25])
        if len(paths) > 25:
            names += f"\n  … and {len(paths) - 25} more"
        ans = QMessageBox.question(
            self,
            "Confirm deletion",
            f"Permanently delete {len(paths)} item(s)?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        sorted_paths = sorted(paths, key=lambda p: len(p.parts), reverse=True)
        for p in sorted_paths:
            try:
                if not p.exists():
                    continue
                if p.is_dir():
                    shutil.rmtree(p)
                elif p.exists():
                    p.unlink()
            except Exception:
                pass
        if self._owner:
            self._owner.refresh()

    # ── Двойной клик → открыть файл ──

    def _on_double_click(self, idx: QModelIndex) -> None:
        proxy_model = self.model()
        if isinstance(proxy_model, QSortFilterProxyModel):
            source_idx = proxy_model.mapToSource(idx)
        else:
            source_idx = idx
        col0 = source_idx.sibling(source_idx.row(), 0)
        p = col0.data(_ROLE_PATH)
        if not isinstance(p, str):
            return
        path = Path(p)
        owner = self._owner
        if owner is not None and path.exists():
            try:
                owner.on_file_double_clicked(path)
                return
            except AttributeError:
                pass
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class _EspFilePreviewEdit(QPlainTextEdit):
    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        owner = getattr(self, "_owner", None)
        if owner is not None and hasattr(owner, "_on_asset_path_clicked"):
            menu.addSeparator()
            action = menu.addAction("Search in mods")

            def on_triggered():
                cursor = self.textCursor()
                block = cursor.block()
                text = block.text() if block.isValid() else ""
                line = text.strip()
                if not line:
                    return
                path = line
                lower = path.lower()
                if ("/" in path or "\\" in path) and lower.endswith(
                    (".nif", ".dds", ".wav", ".xwm", ".hkx", ".pex")
                ):
                    owner._on_asset_path_clicked(path)

            action.triggered.connect(on_triggered)

        menu.exec(event.globalPos())




# ── Основной виджет ───────────────────────────────────────────────────


class ModFilesWidget(QWidget):
    def __init__(
        self, organizer: mobase.IOrganizer, parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._org = organizer
        self._mod_view: Optional[QTreeView] = None
        self._selection_connection = None  # храним ссылку на соединение
        self._current: Optional[str] = None
        self._root: Optional[Path] = None
        self._pending: Optional[str] = None
        self._tab_widget: Optional[QTabWidget] = None
        self._pending_refresh = False

        # Debounce: при быстром переключении модов перестраиваем дерево
        # только для последнего выбранного мода
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(100)
        self._debounce.timeout.connect(self._apply_pending)

        self._dds_available = _load_dds_modules()
        self._dds_options = DDSOptions() if self._dds_available else None
        self._channel_manager = (
            DDSChannelManager(ColourChannels.RGBA) if self._dds_available else None
        )
        self._current_dds_widget = None
        self._preview_forced_hidden = True
        self._pending_preview_path: Optional[str] = None
        self._channel_initialized = False
        self._rebuilding = False
        self._rebuild_token = 0
        self._preview_text_limit = 256 * 1024
        self._preview_hex_limit = 128 * 1024
        self._esp_preview_cache = {}

        self._preview_debounce = QTimer(self)
        self._preview_debounce.setSingleShot(True)
        self._preview_debounce.setInterval(150)
        self._preview_debounce.timeout.connect(self._apply_pending_preview)

        self._build_ui()
        self.destroyed.connect(self._on_destroyed)

    def on_file_double_clicked(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix in {".esp", ".esm", ".esl"}:
            self._open_esp_viewer(path)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_esp_viewer(self, path: Path) -> None:
        if not path.is_file():
            return
        try:
            import importlib
            import sys
            from pathlib import Path

            # 1. Обеспечиваем доступность esp_viewer в sys.path
            base_dir = Path(__file__).parent.absolute()
            if str(base_dir) not in sys.path:
                sys.path.insert(0, str(base_dir))

            # 2. Пытаемся импортировать основной модуль
            pkg = __package__ or __name__.rpartition(".")[0]
            esp_pkg_name = f"{pkg}.esp_viewer" if pkg else "esp_viewer"
            
            try:
                # Сначала пробуем через пакетный префикс (как в MO2)
                esp_pkg = importlib.import_module(esp_pkg_name)
            except ImportError:
                # Если не вышло, пробуем напрямую (мы добавили путь в sys.path)
                esp_pkg = importlib.import_module("esp_viewer")

            # 3. Магия для абсолютных импортов внутри пакета
            if "esp_viewer" not in sys.modules:
                sys.modules["esp_viewer"] = esp_pkg
            
            # Прописываем основные подпакеты, чтобы from esp_viewer.core... работало
            for sub in ("core", "ui", "formatting", "utils"):
                full_sub_name = f"{esp_pkg.__name__}.{sub}"
                try:
                    sub_mod = importlib.import_module(full_sub_name)
                    sys.modules[f"esp_viewer.{sub}"] = sub_mod
                except Exception:
                    pass

            # 4. Запуск
            main_mod_name = f"{esp_pkg.__name__}.main"
            main_mod = importlib.import_module(main_mod_name)
            launch_viewer = getattr(main_mod, "launch_viewer")
            parent = self.window() if hasattr(self, "window") else None
            launch_viewer(str(path), language=None, parent=parent)

        except Exception as e:
            import traceback
            logger.error(f"Failed to launch esp_viewer for {path}: {e}")
            logger.error(traceback.format_exc())
            # Не вызываем QDesktopServices.openUrl для плагинов, чтобы избежать ShellExecute error 5
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "ESP Viewer Error", f"Could not open plugin viewer:\n{e}")

    def _get_esp_viewer_script(self) -> Optional[Path]:
        base = Path(__file__).resolve().parent
        # 1) Вариант: esp_viewer как соседняя папка рядом с ModFilesTab
        script = base.parent / "esp_viewer" / "main.py"
        if script.is_file():
            return script
        # 2) Вариант: esp_viewer вложен внутрь ModFilesTab/esp_viewer
        script2 = base / "esp_viewer" / "main.py"
        if script2.is_file():
            return script2
        return None

    def _get_python_executable(self) -> str:
        org = self._org
        if org is not None:
            try:
                value = org.pluginSetting("Mod Files Tab", "espViewerPythonPath")
                if isinstance(value, str) and value:
                    return value
            except Exception:
                pass
        return "python"

    # ── Построение UI ──

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Заголовок
        self._label = QLabel("No mod selected")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        # Панель инструментов
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter files…")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_edit, 1)

        btn_expand = QPushButton("Expand")
        btn_expand.setFixedWidth(64)
        btn_expand.clicked.connect(lambda: self._tree.expandAll())
        toolbar.addWidget(btn_expand)

        btn_collapse = QPushButton("Collapse")
        btn_collapse.setFixedWidth(64)
        btn_collapse.clicked.connect(lambda: self._tree.collapseAll())
        toolbar.addWidget(btn_collapse)

        btn_refresh = QPushButton("↻")
        btn_refresh.setToolTip("Refresh (F5)")
        btn_refresh.setFixedWidth(28)
        btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(btn_refresh)

        layout.addLayout(toolbar)

        # Модель → прокси → дерево
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Name", "Size", "Type"])

        self._proxy = _SortProxy(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(0)
        self._proxy.setRecursiveFilteringEnabled(True)

        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.splitterMoved.connect(self._save_splitter_state)

        self._tree = _FilesTree(self)
        self._tree.set_owner(self)
        self._tree.setModel(self._proxy)
        self._tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self._preview_panel = QWidget(self._splitter)
        preview_layout = QVBoxLayout(self._preview_panel)
        preview_layout.setContentsMargins(4, 4, 4, 4)
        preview_layout.setSpacing(4)

        preview_header = QHBoxLayout()
        self._preview_label = QLabel("No file selected")
        self._preview_label.setWordWrap(True)
        preview_header.addWidget(self._preview_label, 1)

        self._preview_channel = QComboBox()
        preview_header.addWidget(self._preview_channel)

        self._preview_close = QPushButton("×")
        self._preview_close.setFixedWidth(24)
        preview_header.addWidget(self._preview_close)

        preview_layout.addLayout(preview_header)

        self._preview_container = QVBoxLayout()
        self._preview_container.setContentsMargins(0, 0, 0, 0)
        self._preview_container.setSpacing(0)
        preview_layout.addLayout(self._preview_container, 1)

        self._splitter.addWidget(self._tree)
        self._splitter.addWidget(self._preview_panel)
        layout.addWidget(self._splitter, 1)

        # Статус
        self._status = QLabel()
        self._status.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._status)

        sel = self._tree.selectionModel()
        if sel:
            sel.currentChanged.connect(self._on_tree_current_changed)

        if self._dds_available:
            self._init_channel_controls()
        else:
            self._preview_channel.addItem("N/A")
            self._preview_channel.setEnabled(False)

        self._preview_close.clicked.connect(self._on_preview_close)
        self._preview_panel.setVisible(False)
        self._set_preview_message("No file selected", False)
        self._restore_splitter_state()

    # ── Публичные методы ──

    def attach_to_mod_list(self, view: QTreeView) -> None:
        """Подписаться на смену выбранного мода. Безопасно при повторном вызове."""
        # Отключить предыдущее соединение
        if self._mod_view is not None:
            try:
                old_sel = self._mod_view.selectionModel()
                if old_sel:
                    old_sel.currentChanged.disconnect(self._on_mod_selection)
            except (TypeError, RuntimeError):
                pass
            self._selection_connection = None

        self._mod_view = view
        sel = view.selectionModel()
        if sel:
            sel.currentChanged.connect(self._on_mod_selection)
            self._selection_connection = sel

    def attach_to_tab_widget(self, tabs: QTabWidget) -> None:
        if self._tab_widget is not None:
            try:
                self._tab_widget.currentChanged.disconnect(self._on_tab_changed)
            except (TypeError, RuntimeError):
                pass
        self._tab_widget = tabs
        tabs.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(tabs.currentIndex())

    def refresh(self) -> None:
        if not self._is_tab_active():
            self._pending_refresh = True
            return
        if self._current and self._root:
            expanded = self._save_expanded_state()
            self._rebuild()                       # ← теперь token необязателен
            self._restore_expanded_state(expanded)

    # ── Сохранение/восстановление состояния раскрытия ──

    def _save_expanded_state(self) -> set[str]:
        expanded: set[str] = set()

        def walk(parent_idx: QModelIndex) -> None:
            for row in range(self._proxy.rowCount(parent_idx)):
                idx = self._proxy.index(row, 0, parent_idx)
                if self._tree.isExpanded(idx):
                    path = idx.data(_ROLE_PATH)
                    if path:
                        expanded.add(path)
                    walk(idx)

        walk(QModelIndex())
        return expanded

    def _restore_expanded_state(self, expanded: set[str]) -> None:
        if not expanded:
            return

        def walk(parent_idx: QModelIndex) -> None:
            for row in range(self._proxy.rowCount(parent_idx)):
                idx = self._proxy.index(row, 0, parent_idx)
                path = idx.data(_ROLE_PATH)
                if path in expanded:
                    self._tree.setExpanded(idx, True)
                    walk(idx)

        walk(QModelIndex())

    def _is_tab_active(self) -> bool:
        if self._tab_widget is None:
            return True
        return self._tab_widget.currentWidget() is self

    def _on_tab_changed(self, _index: int) -> None:
        if not self._is_tab_active():
            self._debounce.stop()
            self._preview_debounce.stop()
            return
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()
        if self._pending:
            self._apply_pending()
        if self._pending_preview_path:
            self._apply_pending_preview()

    # ── Слоты ──

    def _on_mod_selection(
        self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        name = self._resolve_mod_name(current)
        if name and name != self._current:
            self._pending = name
            _log("MOD", f"selection pending={name}")
            if not self._is_tab_active():
                return
            self._debounce.start()

    def _apply_pending(self) -> None:
        if not self._is_tab_active():
            return
        if self._pending:
            try:
                _log("MOD", f"apply pending={self._pending}")
                self._show_mod(self._pending)
            except RuntimeError:
                _log("MOD", "apply pending runtimeerror")
                return
            finally:
                self._pending = None

    def _on_filter_changed(self, text: str) -> None:
        self._proxy.setFilterRegularExpression(
            QRegularExpression(
                QRegularExpression.escape(text),
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
        )
        if text:
            self._tree.expandAll()

    def _on_tree_current_changed(
        self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        if self._rebuilding or current.model() is not self._tree.model():
            return
        self._pending_preview_path = self._path_from_proxy_index(current)
        _log("PREVIEW", f"tree current path={self._pending_preview_path}")
        if not self._is_tab_active():
            return
        self._preview_debounce.start()

    def _apply_pending_preview(self) -> None:
        try:
            if not self._is_tab_active():
                return
            path = self._pending_preview_path
            self._pending_preview_path = None
            if not path:
                _log("PREVIEW", "apply pending empty")
                self._set_preview_message("No file selected", False)
                return

            p = Path(path)
            if not p.is_file():
                _log("PREVIEW", f"apply pending not file path={p}")
                self._set_preview_message(
                    "Not a file", not self._preview_forced_hidden
                )
                return

            if p.suffix.lower() != ".dds":
                self._preview_forced_hidden = False
                self._preview_panel.setVisible(True)
                self._preview_channel.setEnabled(False)
                if self._try_image_preview(p):
                    return
                self._load_text_or_hex_preview(p)
                return

            if not self._dds_available:
                self._dds_available = _load_dds_modules()
            if not self._dds_available:
                message = "DDS Preview not available"
                if _DDS_PREVIEW_ERROR:
                    message = f"DDS Preview not available: {_DDS_PREVIEW_ERROR}"
                _log("PREVIEW", f"dds unavailable message={message}")
                self._set_preview_message(message, True)
                return
            if self._dds_options is None:
                self._dds_options = DDSOptions()
            if self._channel_manager is None:
                self._channel_manager = DDSChannelManager(ColourChannels.RGBA)
            self._init_channel_controls()

            self._preview_forced_hidden = False
            self._preview_panel.setVisible(True)
            _log("PREVIEW", f"load dds path={p}")
            self._load_dds_preview(p)
        except RuntimeError:
            _log("PREVIEW", "apply pending runtimeerror")
            return
        except Exception as exc:
            _log("PREVIEW", f"apply pending error={exc}")
            self._set_preview_message(f"Preview error: {exc}", True)

    def _try_image_preview(self, path: Path) -> bool:
        self._clear_current_dds_widget()
        self._clear_preview_container()

        reader = QImageReader(str(path))
        if not reader.canRead():
            return False

        image = reader.read()
        if image.isNull():
            return False

        pixmap = QPixmap.fromImage(image)
        label = QLabel(self._preview_panel)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(pixmap)

        scroll = QScrollArea(self._preview_panel)
        scroll.setWidgetResizable(True)
        scroll.setWidget(label)
        self._preview_container.addWidget(scroll, 1)

        fmt = self._qbytearray_to_str(reader.format())
        parts = [f"{image.width()}x{image.height()}"]
        if fmt:
            parts.append(fmt.upper())
        self._preview_label.setText(f"{path.name} — {' '.join(parts)}")
        return True

    def _load_text_or_hex_preview(self, path: Path) -> None:
        self._clear_current_dds_widget()
        self._clear_preview_container()

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        if size == 0:
            self._set_preview_message(f"{path.name} — empty file", True)
            return

        suffix = path.suffix.lower()
        if suffix in {".esp", ".esm", ".esl"}:
            self._load_esp_preview(path)
            return

        if suffix == ".bsa":
            preview = build_bsa_preview(path)
            if preview is not None:
                title, text = preview
                raw = text.encode("utf-8", errors="replace")
                if len(raw) > self._preview_text_limit:
                    raw = raw[: self._preview_text_limit]
                self._show_text_preview(path, raw, len(text.encode("utf-8", errors="replace")))
                self._preview_label.setText(f"{path.name} — {title}")
                return

        if suffix == ".nif":
            preview = build_nif_preview(path)
            if preview is not None:
                title, text = preview
                raw = text.encode("utf-8", errors="replace")
                if len(raw) > self._preview_text_limit:
                    raw = raw[: self._preview_text_limit]
                self._show_text_preview(path, raw, len(text.encode("utf-8", errors="replace")))
                self._preview_label.setText(f"{path.name} — {title}")
                return

        if suffix == ".pex":
            preview = build_pex_preview(path)
            if preview is not None:
                title, text = preview
                raw = text.encode("utf-8", errors="replace")
                if len(raw) > self._preview_text_limit:
                    raw = raw[: self._preview_text_limit]
                self._show_text_preview(path, raw, len(text.encode("utf-8", errors="replace")))
                self._preview_label.setText(f"{path.name} — {title}")
                return

        if suffix == ".hkx":
            preview = build_hkx_preview(path)
            if preview is not None:
                title, text = preview
                raw = text.encode("utf-8", errors="replace")
                if len(raw) > self._preview_text_limit:
                    raw = raw[: self._preview_text_limit]
                self._show_text_preview(path, raw, len(text.encode("utf-8", errors="replace")))
                self._preview_label.setText(f"{path.name} — {title}")
                return

        raw = self._read_preview_bytes(path, self._preview_text_limit)
        if self._is_text_data(raw, suffix):
            self._show_text_preview(path, raw, size)
            return

        raw = self._read_preview_bytes(path, self._preview_hex_limit)
        self._show_hex_preview(path, raw, size)

    def _load_esp_preview(self, path: Path) -> None:
        self._clear_current_dds_widget()
        self._clear_preview_container()

        if not hasattr(self, "_esp_preview_cache"):
            self._esp_preview_cache = {}

        key = str(path)
        text = self._esp_preview_cache.get(key)

        if text is None:
            try:
                import importlib
                import sys
                from pathlib import Path

                # 1. Обеспечиваем доступность esp_viewer в sys.path
                base_dir = Path(__file__).parent.absolute()
                if str(base_dir) not in sys.path:
                    sys.path.insert(0, str(base_dir))

                # 2. Пытаемся импортировать основной пакет
                pkg = __package__ or __name__.rpartition(".")[0]
                esp_pkg_name = f"{pkg}.esp_viewer" if pkg else "esp_viewer"
                
                try:
                    esp_pkg = importlib.import_module(esp_pkg_name)
                except ImportError:
                    esp_pkg = importlib.import_module("esp_viewer")

                # 3. Магия для абсолютных импортов
                if "esp_viewer" not in sys.modules:
                    sys.modules["esp_viewer"] = esp_pkg
                
                for sub in ("core", "ui", "formatting", "utils"):
                    full_sub_name = f"{esp_pkg.__name__}.{sub}"
                    try:
                        sub_mod = importlib.import_module(full_sub_name)
                        sys.modules[f"esp_viewer.{sub}"] = sub_mod
                    except Exception:
                        pass

                # Теперь импорты должны работать
                from esp_viewer.core.plugin_file import parse_plugin
                from esp_viewer.core.search_engine import iter_records
                from esp_viewer.formatting.record_formatter import (
                    StructuredSubrecordParser,
                )
            except Exception as exc:
                import traceback
                logger.error(f"Failed to load esp_viewer for preview: {exc}\n{traceback.format_exc()}")
                self._set_preview_message(f"ESP preview error: {exc}", True)
                return

            try:
                plugin = parse_plugin(key)
            except Exception as exc:
                self._set_preview_message(f"ESP parse error: {exc}", True)
                return

            sig_counts = Counter()
            total_records = 0
            full_names = set()
            asset_paths = set()
            form_ids = set()

            for record in iter_records(plugin.children):
                sig_counts[record.signature] += 1
                total_records += 1
                form_ids.add(record.form_id)
                if record.full_name:
                    full_names.add(record.full_name)
                try:
                    parser = StructuredSubrecordParser(record, plugin)
                    for node in parser.iter_nodes():
                        value = getattr(node, "value", None)
                        if not value:
                            continue
                        lower = value.lower()
                        if not ("/" in value or "\\" in value):
                            continue
                        if lower.endswith((".nif", ".dds", ".wav", ".xwm", ".hkx", ".pex")):
                            asset_paths.add(value)
                except Exception:
                    pass

            lines = []
            lines.append(f"ESL: {'Yes' if plugin.is_esl else 'No'}")
            lines.append(f"Localized: {'Yes' if plugin.localized else 'No'}")
            if plugin.masters:
                lines.append("")
                lines.append("Masters:")
                max_masters = 12
                for name in plugin.masters[:max_masters]:
                    lines.append(f"  - {name}")
                if len(plugin.masters) > max_masters:
                    lines.append(
                        f"  ... and {len(plugin.masters) - max_masters} more"
                    )

            lines.append("")
            lines.append("FormID:")
            if form_ids:
                min_id = min(form_ids)
                max_id = max(form_ids)
                lines.append(f"  Unique: {len(form_ids)}")
                lines.append(f"  Range: 0x{min_id:08X} - 0x{max_id:08X}")
            else:
                lines.append("  No FormIDs detected")

            lines.append("")
            lines.append(f"Records: {total_records}")
            if sig_counts:
                lines.append("")
                lines.append("By signature:")
                for sig, count in sorted(
                    sig_counts.items(), key=lambda item: (-item[1], item[0])
                )[:20]:
                    lines.append(f"  {sig}: {count}")

            lines.append("")
            lines.append("File paths in records:")
            if asset_paths:
                for value in sorted(asset_paths):
                    lines.append(f"  {value}")
            else:
                lines.append("  (none detected)")

            lines.append("")
            lines.append("Display Names (FULL):")
            if full_names:
                for name in sorted(full_names):
                    lines.append(f"  {name}")
            else:
                lines.append("  (none detected)")

            text = "\n".join(lines)
            if len(self._esp_preview_cache) > 8:
                self._esp_preview_cache.clear()
            self._esp_preview_cache[key] = text

        editor = _EspFilePreviewEdit(self, self._preview_panel)
        editor.setPlainText(text)
        self._preview_container.addWidget(editor, 1)
        self._preview_label.setText(f"{path.name} — ESP/ESM/ESL preview")

    def _on_asset_path_clicked(self, asset_path: str) -> None:
        filename = Path(asset_path).name
        if not filename:
            return
        mods = self._find_mods_with_file(filename)
        self._show_file_search_dialog(filename, mods)

    def _find_mods_with_file(self, filename: str) -> dict[str, list[str]]:
        mods: dict[str, list[str]] = {}
        if self._org is None:
            return mods

        mod_list = self._org.modList()
        all_mods = mod_list.allMods()

        search_lower = filename.lower()
        ext = os.path.splitext(search_lower)[1]
        extensions = [ext] if ext else []

        for mod_name in all_mods:
            state = mod_list.state(mod_name)
            if not (state & mobase.ModState.EXISTS):
                continue

            mod_info = self._org.getMod(mod_name)
            if not mod_info:
                continue

            mod_path = mod_info.absolutePath()
            if not mod_path or not os.path.exists(mod_path):
                continue

            found_paths: list[str] = []
            try:
                for root, _, files in os.walk(mod_path):
                    for file_name in files:
                        file_lower = file_name.lower()

                        if extensions:
                            file_ext = os.path.splitext(file_lower)[1]
                            if file_ext and file_ext not in extensions:
                                continue

                        if search_lower in file_lower or fnmatch.fnmatch(
                            file_lower, f"*{search_lower}*"
                        ):
                            full_path = os.path.join(root, file_name)
                            relative_path = os.path.relpath(full_path, mod_path)
                            found_paths.append(relative_path)
            except Exception:
                continue

            if found_paths:
                # уникальные и отсортированные пути
                unique_sorted = sorted(dict.fromkeys(found_paths))
                mods[mod_name] = unique_sorted

        return mods

    def _show_file_search_dialog(self, filename: str, mods: dict[str, list[str]]) -> None:
        parent = self.window() or self
        if not mods:
            QMessageBox.information(
                parent,
                "File search",
                f"File '{filename}' not found in any mod",
            )
            return
        dialog = QDialog(parent)
        dialog.setWindowTitle(f"File search: {filename}")
        layout = QVBoxLayout(dialog)
        label = QLabel(
            f"File '{filename}' found in {len(mods)} mod(s):",
            dialog,
        )
        layout.addWidget(label)

        tree = QTreeWidget(dialog)
        tree.setHeaderLabels(["Mod", "File path"])
        header = tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # наполняем дерево: мод → найденные относительные пути
        for mod_name, paths in mods.items():
            parent_item = QTreeWidgetItem([mod_name, ""])
            tree.addTopLevelItem(parent_item)
            for rel in paths:
                child = QTreeWidgetItem(["", rel])
                parent_item.addChild(child)
            parent_item.setExpanded(True)

        tree.itemActivated.connect(lambda item, _col: on_item_activated(item))
        tree.itemDoubleClicked.connect(lambda item, _col: on_item_activated(item))

        layout.addWidget(tree)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            dialog,
        )
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        # увеличить окно в 2 раза относительно прежнего: условно 800x600
        dialog.resize(800, 600)

        def on_item_activated(item):
            if item is None:
                return
            # если клик по потомку — берём родителя (имя мода)
            parent_item = item.parent()
            name = item.text(0) if parent_item is None else parent_item.text(0)
            if not name:
                return
            dialog.accept()
            self._scroll_to_mod(name)

        dialog.exec()

    def _scroll_to_mod(self, name: str) -> None:
        if self._mod_view is None:
            return
        view = self._mod_view
        model = view.model()
        if model is None:
            return
        # поиск индекса через match, как в autoscroller
        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            name,
            1,
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )
        if not matches:
            return
        index = matches[0]

        # обеспечить разворачивание родителей (на случай групп)
        parent = index.parent()
        while parent.isValid():
            view.expand(parent)
            parent = parent.parent()

        # плавная прокрутка к центру, близко к логике autoscroller
        scrollbar = view.verticalScrollBar()
        if not scrollbar:
            view.setCurrentIndex(index)
            view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
            view.setFocus()
            return

        start = scrollbar.value()
        view.setCurrentIndex(index)
        view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        end = scrollbar.value()
        if start == end:
            view.setFocus()
            return
        scrollbar.setValue(start)
        anim = QPropertyAnimation(scrollbar, b"value", view)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        view._esp_anim = anim
        anim.start()
        view.setFocus()

    def _read_preview_bytes(self, path: Path, limit: int) -> bytes:
        try:
            with path.open("rb") as handle:
                return handle.read(limit)
        except Exception:
            return b""

    def _is_text_data(self, sample: bytes, suffix: str) -> bool:
        text_exts = {
            ".txt",
            ".ini",
            ".cfg",
            ".conf",
            ".json",
            ".xml",
            ".yaml",
            ".yml",
            ".toml",
            ".log",
            ".psc",
            ".html",
            ".htm",
            ".csv",
            ".tsv",
        }
        if suffix in text_exts:
            return True
        if not sample:
            return False
        if b"\x00" in sample:
            return False
        nontext = 0
        for b in sample:
            if b < 9 or (b > 13 and b < 32):
                nontext += 1
        return (nontext / len(sample)) < 0.2

    def _show_text_preview(self, path: Path, raw: bytes, size: int) -> None:
        text = raw.decode("utf-8", errors="replace")
        editor = QPlainTextEdit(self._preview_panel)
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setPlainText(text)
        self._preview_container.addWidget(editor, 1)

        shown = len(raw)
        suffix = ""
        if size > shown:
            suffix = f" (showing {_human_size(shown)} of {_human_size(size)})"
        self._preview_label.setText(f"{path.name} — Text preview{suffix}")

    def _show_hex_preview(self, path: Path, raw: bytes, size: int) -> None:
        editor = QPlainTextEdit(self._preview_panel)
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setPlainText(self._format_hex_dump(raw))
        self._preview_container.addWidget(editor, 1)

        shown = len(raw)
        suffix = ""
        if size > shown:
            suffix = f" (showing {_human_size(shown)} of {_human_size(size)})"
        self._preview_label.setText(f"{path.name} — Hex preview{suffix}")

    def _format_hex_dump(self, data: bytes) -> str:
        lines: list[str] = []
        for offset in range(0, len(data), 16):
            chunk = data[offset : offset + 16]
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            ascii_part = "".join(
                chr(b) if 32 <= b < 127 else "." for b in chunk
            )
            lines.append(f"{offset:08X}  {hex_part:<47}  {ascii_part}")
        return "\n".join(lines)

    def _qbytearray_to_str(self, value: QByteArray) -> str:
        try:
            return bytes(value).decode("ascii", "ignore")
        except Exception:
            try:
                return value.data().decode("ascii", "ignore")
            except Exception:
                return ""

    def _on_channel_changed(self) -> None:
        if self._rebuilding or not self._dds_available or self._dds_options is None:
            return
        channel = self._preview_channel.currentData()
        if channel is None:
            return
        if self._channel_manager is not None:
            self._channel_manager.setChannels(self._dds_options, channel)
        _log("PREVIEW", f"channel changed={channel}")
        if self._current_dds_widget is not None:
            self._current_dds_widget.update()

    def _init_channel_controls(self) -> None:
        if not self._dds_available or self._channel_initialized:
            return
        self._preview_channel.clear()
        for channel in (
            ColourChannels.RGBA,
            ColourChannels.RGB,
            ColourChannels.R,
            ColourChannels.G,
            ColourChannels.B,
            ColourChannels.A,
        ):
            self._preview_channel.addItem(channel.name, channel)
        self._preview_channel.currentIndexChanged.connect(self._on_channel_changed)
        self._preview_channel.setEnabled(True)
        self._channel_initialized = True

    def _on_preview_close(self) -> None:
        self._preview_forced_hidden = True
        self._preview_panel.setVisible(False)

    def _set_preview_message(self, text: str, show_panel: bool) -> None:
        self._clear_current_dds_widget()
        self._clear_preview_container()
        label = QLabel(text, self._preview_panel)
        label.setWordWrap(True)
        self._preview_container.addWidget(label, 1)
        self._preview_label.setText(text)
        self._preview_channel.setEnabled(False)
        if show_panel:
            self._preview_panel.setVisible(True)

    def _clear_preview_container(self) -> None:
        while self._preview_container.count():
            item = self._preview_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _clear_current_dds_widget(self) -> None:
        w = self._current_dds_widget
        if w is not None:
            self._current_dds_widget = None
            _log("PREVIEW", f"clear dds widget={hex(id(w))}")
            try:
                w.setVisible(False)
            except Exception:
                pass
            try:
                idx = self._preview_container.indexOf(w)
                if idx >= 0:
                    self._preview_container.takeAt(idx)
            except Exception:
                pass
            try:
                if not getattr(w, "clean", True):
                    w.cleanup()
            except Exception:
                pass
            w.deleteLater()

    def _load_dds_preview(self, path: Path) -> None:
        self._clear_current_dds_widget()
        self._clear_preview_container()

        try:
            dds = DDSFile.fromFile(str(path))
            dds.load()
            widget = DDSWidget(dds, self._dds_options)
        except Exception as exc:
            _log("PREVIEW", f"dds load failed path={path} error={exc}")
            self._set_preview_message(f"DDS load failed: {exc}", True)
            return

        self._current_dds_widget = widget
        self._preview_container.addWidget(widget, 1)
        _log("PREVIEW", f"dds widget created={hex(id(widget))} path={path}")
        self._preview_label.setText(f"{path.name} — {dds.getDescription()}")
        if self._dds_available:
            self._preview_channel.setEnabled(True)
        if not self._preview_forced_hidden:
            self._preview_panel.setVisible(True)

    def _restore_splitter_state(self) -> None:
        settings = QSettings("ModFilesTab", "preview_splitter")
        state = settings.value("state")
        if isinstance(state, QByteArray) and not state.isEmpty():
            try:
                if self._splitter.restoreState(state):
                    return
            except Exception:
                pass
        self._splitter.setSizes([70, 30])

    def _save_splitter_state(self) -> None:
        settings = QSettings("ModFilesTab", "preview_splitter")
        settings.setValue("state", self._splitter.saveState())

    def _on_destroyed(self, *_args) -> None:
        self._debounce.stop()
        self._preview_debounce.stop()
        try:
            self._save_splitter_state()
        except (RuntimeError, AttributeError):
            pass
        try:
            self._clear_current_dds_widget()
        except (RuntimeError, AttributeError):
            pass

    def _path_from_proxy_index(self, proxy_idx: QModelIndex) -> Optional[str]:
        if not proxy_idx.isValid():
            return None
        proxy_model = self._tree.model()
        if isinstance(proxy_model, QSortFilterProxyModel):
            source_idx = proxy_model.mapToSource(proxy_idx)
        else:
            source_idx = proxy_idx
        col0 = source_idx.sibling(source_idx.row(), 0)
        val = col0.data(_ROLE_PATH)
        return val if isinstance(val, str) and val else None

    def _reset_preview_on_mod_change(self) -> None:
        self._preview_debounce.stop()
        self._pending_preview_path = None
        self._preview_forced_hidden = True
        _log("PREVIEW", "reset preview on mod change")
        self._set_preview_message("No file selected", False)
        self._preview_panel.setVisible(False)

    # ── Внутренняя логика ──

    def _resolve_mod_name(self, idx: QModelIndex) -> Optional[str]:
        """Получить имя мода из индекса списка модов (всегда столбец 0)."""
        if not idx.isValid() or not self._mod_view:
            return None
        model = self._mod_view.model()
        if model is None:
            return None
        name_idx = model.index(idx.row(), 0, idx.parent())
        val = name_idx.data(Qt.ItemDataRole.DisplayRole)
        if isinstance(val, str) and val.strip():
            return val.strip()
        return None

    def _show_mod(self, name: str) -> None:
        self._root = _mod_directory(self._org, name)
        if self._root is None:
            _log("MOD", f"show mod failed name={name}")
            return
        self._current = name
        self._rebuild_token += 1
        token = self._rebuild_token
        _log("MOD", f"show mod name={name} root={self._root}")
        self._reset_preview_on_mod_change()
        self._tree.set_root(self._root)
        self._label.setText(name)
        self._label.setToolTip(str(self._root) if self._root else "directory not found")
        self._filter_edit.clear()
        self._rebuild(token)

    def _rebuild(self, token: int = None) -> None:
        if token is None:
            self._rebuild_token += 1
            token = self._rebuild_token

        self._rebuilding = True
        self._preview_debounce.stop()
        self._pending_preview_path = None

        sel = self._tree.selectionModel()
        if sel:
            sel.blockSignals(True)

        self._tree.setUpdatesEnabled(False)
        self._tree.setSortingEnabled(False)

        # ═══ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ═══
        # Отсоединяем прокси, чтобы она не хранила устаревший маппинг
        self._proxy.setSourceModel(None)

        _log("MODEL", "rebuild start")

        try:
            _log("MODEL", "rebuild clear model")
            self._model.clear()
            self._model.setHorizontalHeaderLabels(["Name", "Size", "Type"])
            _log("MODEL", "rebuild model headers set")

            if token != self._rebuild_token:
                return

            if not self._root or not self._root.is_dir():
                self._status.setText(
                    "Directory not found" if self._current else ""
                )
                return

            _log("MODEL", f"rebuild root={self._root}")

            style = self.style()
            icon_dir = (
                style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
                if style else QIcon()
            )
            icon_file = (
                style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                if style else QIcon()
            )

            file_count = 0
            total_bytes = 0
            dir_items: dict[Path, QStandardItem] = {}
            walk_dirs = 0

            def ensure_dir(path: Path) -> Optional[QStandardItem]:
                if path == self._root:
                    return None
                if path in dir_items:
                    return dir_items[path]
                parent_item = ensure_dir(path.parent)
                item = QStandardItem(icon_dir, path.name)
                item.setData(str(path), _ROLE_PATH)
                item.setData(True, _ROLE_IS_DIR)
                item.setData(0, _ROLE_SIZE)
                row = [item, QStandardItem(""), QStandardItem("<dir>")]
                if parent_item is None:
                    self._model.appendRow(row)
                else:
                    parent_item.appendRow(row)
                dir_items[path] = item
                return item

            try:
                for dirpath, dirnames, filenames in os.walk(
                    self._root, followlinks=False
                ):
                    if token != self._rebuild_token:
                        return
                    dirnames.sort(key=str.lower)
                    filenames.sort(key=str.lower)
                    dp = Path(dirpath)
                    walk_dirs += 1
                    if walk_dirs == 1 or walk_dirs % 200 == 0:
                        _log("MODEL", f"walk dir={dp}")
                    parent_item = ensure_dir(dp)

                    for fname in filenames:
                        if token != self._rebuild_token:
                            return
                        full = dp / fname
                        try:
                            sz = full.stat().st_size
                        except OSError:
                            sz = 0

                        ext = full.suffix.lower() or "(none)"
                        name_item = QStandardItem(icon_file, fname)
                        name_item.setData(str(full), _ROLE_PATH)
                        name_item.setData(False, _ROLE_IS_DIR)
                        name_item.setData(sz, _ROLE_SIZE)

                        size_item = QStandardItem(_human_size(sz))
                        size_item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter
                        )
                        type_item = QStandardItem(ext)

                        row = [name_item, size_item, type_item]
                        if parent_item is None:
                            self._model.appendRow(row)
                        else:
                            parent_item.appendRow(row)

                        file_count += 1
                        total_bytes += sz
            except OSError:
                pass

            _log("MODEL", f"walk end dirs={walk_dirs} files={file_count} bytes={total_bytes}")

            if token != self._rebuild_token:
                return

            dir_count = len(dir_items)
            parts: list[str] = []
            parts.append(f"{file_count} file{'s' if file_count != 1 else ''}")
            if dir_count:
                parts.append(f"{dir_count} folder{'s' if dir_count != 1 else ''}")
            parts.append(_human_size(total_bytes))
            self._status.setText("  ·  ".join(parts))

        finally:
            _log("MODEL", "finally: reattach proxy")

            # Присоединяем обратно — прокси строит маппинг с нуля
            self._proxy.setSourceModel(self._model)

            # Заголовки сбрасываются при modelReset — восстанавливаем
            header = self._tree.header()
            if header.count() >= 3:
                header.setStretchLastSection(False)
                header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

            if sel:
                sel.blockSignals(False)

            # Включаем сортировку обратно — Qt вызовет proxy.sort() с актуальными данными
            self._tree.setSortingEnabled(True)
            self._tree.setUpdatesEnabled(True)
            self._rebuilding = False
            _log("MODEL", "rebuild end")





# ── Класс плагина ────────────────────────────────────────────────────


class ModFilesTabPlugin(mobase.IPluginTool):
    NAME = "File Explorer"

    def __init__(self):
        super().__init__()
        self._org: Optional[mobase.IOrganizer] = None
        self._window = None
        self._widget: Optional[ModFilesWidget] = None
        self._injected = False
        self._attempts = 0
        self._view_action: Optional[QAction] = None

    # ── IPlugin ──

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._org = organizer
        organizer.onUserInterfaceInitialized(self._on_ui_ready)
        return True

    def name(self) -> str:
        return self.NAME

    def author(self) -> str:
        return "ModFilesTab"

    def description(self) -> str:
        return (
            "Per-mod file browser tab with drag-and-drop, "
            "filtering, sorting, and context menu."
        )

    def version(self) -> mobase.VersionInfo:
        try:
            return mobase.VersionInfo(1, 2, 0, mobase.ReleaseType.FINAL)
        except AttributeError:
            return mobase.VersionInfo(1, 2, 0)

    def requirements(self) -> list:
        return []

    def isActive(self) -> bool:
        return True

    def settings(self) -> list[mobase.PluginSetting]:
        return [
            mobase.PluginSetting(
                "espViewerPythonPath",
                "Python executable with PySide6 for esp_viewer",
                "python",
            )
        ]

    # ── IPluginTool ──

    def displayName(self) -> str:
        return self.NAME

    def tooltip(self) -> str:
        return self.description()

    def icon(self) -> QIcon:
        return QIcon()

    def display(self) -> None:
        """При вызове из меню Tools переключиться на вкладку."""
        if not self._widget:
            return
        parent = self._widget.parent()
        while parent and not isinstance(parent, QTabWidget):
            parent = parent.parent()
        if isinstance(parent, QTabWidget):
            idx = parent.indexOf(self._widget)
            if idx >= 0:
                parent.setCurrentIndex(idx)

    def _find_view_menu(self):
        if not self._window:
            return None
        mb = getattr(self._window, "menuBar", None)
        if not callable(mb):
            return None
        menubar = mb()
        if menubar is None:
            return None
        for act in menubar.actions():
            if not act or not act.menu():
                continue
            t = act.text().replace("&", "").strip().lower()
            if t in ("view", "вид"):
                return act.menu()
        return None

    def _ensure_view_menu_action(self) -> None:
        menu = self._find_view_menu()
        if not menu:
            return
        if self._view_action is None:
            self._view_action = QAction("File Explorer", menu)
            self._view_action.setCheckable(True)
            self._view_action.toggled.connect(self._on_view_toggled)
            menu.addAction(self._view_action)
        self._sync_view_menu_checked()

    def _get_tab_index(self):
        if not self._window:
            return None, -1
        tw = _find_right_pane(self._window)
        if not tw:
            return None, -1
        for i in range(tw.count()):
            if tw.tabText(i) == _TAB_LABEL:
                return tw, i
        return tw, -1

    def _sync_view_menu_checked(self) -> None:
        if not self._view_action:
            return
        tw, idx = self._get_tab_index()
        if not tw or idx < 0:
            self._view_action.setChecked(False)
            return
        tb = tw.tabBar()
        visible = True
        try:
            visible = tb.isTabVisible(idx)
        except Exception:
            visible = True
        self._view_action.setChecked(bool(visible))

    def _on_view_toggled(self, checked: bool) -> None:
        tw, idx = self._get_tab_index()
        if not tw or idx < 0:
            return
        tb = tw.tabBar()
        try:
            tb.setTabVisible(idx, bool(checked))
        except Exception:
            pass
        if not checked and tw.currentIndex() == idx:
            for j in range(tw.count()):
                if j == idx:
                    continue
                ok = True
                try:
                    ok = tw.tabBar().isTabVisible(j)
                except Exception:
                    ok = True
                if ok:
                    tw.setCurrentIndex(j)
                    break

    # ── Инъекция вкладки ──

    def _on_ui_ready(self, main_window) -> None:
        self._window = main_window
        QTimer.singleShot(800, self._try_inject)
        QTimer.singleShot(800, self._ensure_view_menu_action)

    def _try_inject(self) -> None:
        if self._injected or not self._window or not self._org:
            return
        self._attempts += 1

        tw = _find_right_pane(self._window)
        if not tw:
            if self._attempts < 25:
                QTimer.singleShot(1500, self._try_inject)
            return

        # Проверка на дубликат
        for i in range(tw.count()):
            if tw.tabText(i) == _TAB_LABEL:
                w = tw.widget(i)
                if isinstance(w, ModFilesWidget):
                    self._widget = w
                    self._widget.attach_to_tab_widget(tw)
                self._injected = True
                self._sync_view_menu_checked()
                return

        self._widget = ModFilesWidget(self._org)
        mod_view = _find_mod_list_view()
        if mod_view:
            self._widget.attach_to_mod_list(mod_view)
        else:
            # mod list ещё не готов — пробуем позже
            QTimer.singleShot(2000, self._retry_attach_mod_list)
        self._widget.attach_to_tab_widget(tw)
        tw.addTab(self._widget, _TAB_LABEL)
        self._injected = True
        self._sync_view_menu_checked()

    def _retry_attach_mod_list(self) -> None:
        if self._widget is None:
            return
        try:
            _ = self._widget.isVisible()
        except RuntimeError:
            self._widget = None
            return
        mod_view = _find_mod_list_view()
        if mod_view:
            self._widget.attach_to_mod_list(mod_view)


def createPlugin() -> mobase.IPluginTool:
    return ModFilesTabPlugin()


    

    

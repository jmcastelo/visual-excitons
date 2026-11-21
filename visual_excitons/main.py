# This Python file uses the following encoding: utf-8
import sys
from pathlib import Path

# Make `visual_excitons` importable when this file is run directly from a
# clone (python visual_excitons/main.py); installed, it already is
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import QApplication

from visual_excitons import __version__
from visual_excitons.core.dataset import datasetFromPaths
from visual_excitons.core.session import SESSION_SUFFIX


def commandLineParser():
    """The arguments of the `visual-excitons` command."""
    parser = argparse.ArgumentParser(
        prog='visual-excitons',
        description='Visual Excitons: excitons computed with Yambo. Opens a dataset or a session, if given.',
        epilog='A folder is searched as File › Open dataset does: the SAVE directory first, then the BSE and GW '
               'directories next to it or, when the folder holds a single SAVE directory (a Visual Workflows '
               'project), anywhere in it. --save, --bse and --qp give directories instead of those found.')
    parser.add_argument('path', nargs='?',
                        help=f'a folder with a dataset, or a session file ({SESSION_SUFFIX})')
    parser.add_argument('--save', metavar='DIR', help='the SAVE directory (with ns.db1)')
    parser.add_argument('--bse', metavar='DIR', help='the BSE directory (with ndb.BS_diago_Q* files)')
    parser.add_argument('--qp', metavar='PATH', help='the QP database, or the directory with it (GW)')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    return parser


def startupRequest(parser, arguments):
    """
    What to open at startup from the command line: None, ('session', path) or
    ('dataset', dataset, where it was looked for, the kinds given explicitly:
    'save', 'diago', 'qp'). Exits through the parser, with a message, when the
    arguments cannot be used.
    """
    args = parser.parse_args(arguments)
    explicit = (args.save, args.bse, args.qp)
    if args.path and args.path.endswith(SESSION_SUFFIX):
        if any(explicit):
            parser.error('--save, --bse and --qp cannot be used with a session')
        if not Path(args.path).expanduser().is_file():
            parser.error(f'No such session: {args.path}')
        return ('session', str(Path(args.path).expanduser().resolve()))
    if not args.path and not any(explicit):
        return None
    try:
        dataset = datasetFromPaths(args.path, *explicit)
    except ValueError as error:
        parser.error(str(error))
    fixed = tuple(key for key, given in zip(('save', 'diago', 'qp'), explicit) if given)
    return ('dataset', dataset, args.path or args.save or args.bse or args.qp, fixed)


def main(argv=None):
    """Start the application (the `visual-excitons` command)."""
    argv = list(sys.argv if argv is None else argv)
    parser = commandLineParser()
    # Help and version need no window (nor a display)
    if any(argument in ('-h', '--help', '--version') for argument in argv[1:]):
        parser.parse_args(argv[1:])

    # All OpenGL contexts share their resources (shaders, buffers), so the 3D
    # items can also be drawn by a separate window, as in image exports
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(argv)
    app.setApplicationName('Visual Excitons')
    app.setApplicationVersion(__version__)
    app.setOrganizationName('VisualExcitons')
    # Qt's own options (-platform, -style...) are taken out of arguments()
    request = startupRequest(parser, app.arguments()[1:])

    from visual_excitons.gui.main_window import MainWindow
    mainWindow = MainWindow()
    mainWindow.show()
    if request is not None:
        QTimer.singleShot(0, lambda: mainWindow.openRequested(request))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

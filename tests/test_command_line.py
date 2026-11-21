"""The `visual-excitons` command line: what it opens at startup (no window needed)."""

import pytest

from visual_excitons.main import commandLineParser, startupRequest
from test_core import makeWorkflowsProject


def request(*arguments):
    return startupRequest(commandLineParser(), [str(argument) for argument in arguments])


def test_nothing_to_open():
    assert request() is None


def test_folder(tmp_path):
    project = makeWorkflowsProject(tmp_path)
    kind, dataset, where, fixed = request(project)
    assert kind == 'dataset' and where == str(project) and fixed == ()
    assert dataset['save'] == str(project / '03-p2y/outputs/SAVE') and dataset['diago'] == str(project / '05-bse/outputs/diago')


def test_folder_and_directories(tmp_path):
    project = makeWorkflowsProject(tmp_path)
    (project / 'other').mkdir()
    (project / 'other/ndb.BS_diago_Q3').touch()
    kind, dataset, where, fixed = request(project, '--bse', project / 'other')
    assert dataset['diago'] == str(project / 'other') and dataset['qpFile'] == 'ndb.QP'
    assert fixed == ('diago',)          # not asked again when the project has several
    kind, dataset, where, fixed = request('--save', project / '03-p2y/outputs/SAVE', '--bse', project / 'other')
    assert where == str(project / '03-p2y/outputs/SAVE') and dataset['qp'] is None
    assert fixed == ('save', 'diago')


def test_session(tmp_path):
    session = tmp_path / 'a.vxsession'
    session.touch()
    assert request(session) == ('session', str(session))


@pytest.mark.parametrize('arguments, message', [
    (['missing.vxsession'], 'No such session'),
    (['{tmp}/a.vxsession', '--bse', '{tmp}'], 'cannot be used with a session'),
    (['{tmp}/missing'], 'Not a folder'),
    (['--save', '{tmp}'], 'No SAVE directory'),
])
def test_errors(tmp_path, capsys, arguments, message):
    (tmp_path / 'a.vxsession').touch()
    with pytest.raises(SystemExit) as exit:
        request(*[argument.format(tmp=tmp_path) for argument in arguments])
    assert exit.value.code == 2 and message in capsys.readouterr().err


def test_help_and_version_need_no_window(capsys):
    from visual_excitons import __version__
    from visual_excitons.main import main
    with pytest.raises(SystemExit):
        main(['visual-excitons', '--version'])
    assert __version__ in capsys.readouterr().out

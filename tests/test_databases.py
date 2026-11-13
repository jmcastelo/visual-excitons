"""Yambo databases recognised by their content, the QP database chosen, and the checks that they belong together."""

import os

import pytest

from visual_excitons.core.databases import identify, qpDatabases, bseFiles, QP, BSE
from visual_excitons.core.consistency import checkDataset, summary, OK, WARNING, ERROR
from visual_excitons.core.options import Options
from conftest import datasetPath, writeQPDatabase, writeBSEDatabase


def test_databases_are_recognised_by_their_content(tmp_path):
    qp = identify(writeQPDatabase(tmp_path / 'my_gw_run.nc', bands=(10, 20), kpoints=7))
    assert qp['kind'] == QP and qp['bands'] == (10, 20) and qp['kpoints'] == 7
    assert identify(writeBSEDatabase(tmp_path / 'BSE_Q5'))['q'] == 4          # named as yambopy reads it
    assert identify(writeBSEDatabase(tmp_path / 'exc.nc'))['q'] is None       # no Q-point in its name
    assert identify(writeQPDatabase(tmp_path / 'ndb.QP_fragment_1')) is None  # fragments are parts
    (tmp_path / 'notes.txt').write_text('not a database')
    assert identify(tmp_path / 'notes.txt') is None
    # Standard BSE names are taken at their word, without opening them
    (tmp_path / 'ndb.BS_diago_Q3').touch()
    assert identify(tmp_path / 'ndb.BS_diago_Q3') == {'kind': BSE, 'path': str(tmp_path / 'ndb.BS_diago_Q3'),
                                                     'name': 'ndb.BS_diago_Q3', 'q': 2, 'opened': False}


def test_default_qp_database(tmp_path):
    writeQPDatabase(tmp_path / 'ndb.QP_1_5', bands=(1, 5))
    writeQPDatabase(tmp_path / 'ndb.QP_merged', bands=(1, 9))
    assert [info['name'] for info in qpDatabases(tmp_path)] == ['ndb.QP_merged', 'ndb.QP_1_5']   # the widest first
    writeQPDatabase(tmp_path / 'ndb.QP', bands=(2, 4))
    assert qpDatabases(tmp_path)[0]['name'] == 'ndb.QP'                                          # ndb.QP if there

    options = Options()
    options.setQPDir(str(tmp_path))
    assert options.qpFile == 'ndb.QP' and '3 QP databases found: using ndb.QP (bands 2–4)' in options.qpStatus()
    options.setQPFile('ndb.QP_1_5')
    assert options.qpFile == 'ndb.QP_1_5'
    options.setQPFile('missing')
    assert options.qpFile == 'ndb.QP_1_5'
    options.setQPDir(str(tmp_path), qpFile='ndb.QP_merged')       # e.g. remembered with the dataset
    assert options.qpFile == 'ndb.QP_merged'


def test_bse_files_and_their_problems(tmp_path):
    for name in ('ndb.BS_diago_Q1', 'ndb.BS_diago_Q2'):
        (tmp_path / name).touch()
    writeBSEDatabase(tmp_path / 'copy_Q2')          # a second database for Q-point 2
    writeBSEDatabase(tmp_path / 'BSE_Q7')           # another name, its Q-point readable
    writeBSEDatabase(tmp_path / 'exc_Gamma.nc')     # its Q-point unknown
    files, problems = bseFiles(tmp_path)
    assert files == {0: 'ndb.BS_diago_Q1', 1: 'ndb.BS_diago_Q2', 6: 'BSE_Q7'}
    assert any('exc_Gamma.nc' in problem and 'does not give its Q-point' in problem for problem in problems)
    assert any('Q-point 2 has two BSE databases' in problem and 'ndb.BS_diago_Q2 is used' in problem
               for problem in problems)


BII3 = 'BiI3_Bulk_8x8x8'


@pytest.mark.data
def test_several_qp_databases_in_a_real_dataset():
    names = [info['name'] for info in qpDatabases(datasetPath(BII3) / 'qp')]
    assert names[0] == 'ndb.QP' and {'ndb.QP_140_146', 'ndb.QP_150_157'} <= set(names)


@pytest.mark.data
def test_checks_of_a_dataset_and_of_mixed_ones(tmp_path):
    folder = datasetPath(BII3)
    files, problems = bseFiles(folder / 'diagos')
    findings = checkDataset(str(folder / 'save'), str(folder / 'qp' / 'ndb.QP'), str(folder / 'diagos'), files, problems)
    texts = [f['text'] for f in findings]
    assert any('was computed on this SAVE directory' in text for text in texts)
    assert summary(findings) == WARNING and any('band 139 had no GW correction' in text for text in texts)

    # A QP database and BSE databases of another system
    mixed = checkDataset(str(datasetPath('BN') / 'save'), str(folder / 'qp' / 'ndb.QP'), str(folder / 'diagos'), files)
    errors = [f['text'] for f in mixed if f['level'] == ERROR]
    assert summary(mixed) == ERROR
    assert any('does not belong to this SAVE directory' in text and 'lattice constants' in text for text in errors)
    assert any('use bands up to 152, but the SAVE directory has 70' in text for text in errors)

    # A BSE database under the name of another Q-point
    (tmp_path / 'ndb.BS_diago_Q5').symlink_to(folder / 'diagos' / 'ndb.BS_diago_Q30')
    wrong = checkDataset(str(folder / 'save'), None, str(tmp_path), {4: 'ndb.BS_diago_Q5'})
    assert any('ndb.BS_diago_Q5: its coordinates are those of Q-point 30' in f['text'] for f in wrong)


@pytest.mark.data
def test_system_panel_offers_the_qp_databases_and_shows_the_checks(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window.openDataset(main_window.findDataset(datasetPath(BII3)))
    system = window.system
    combo = system.qpFileComboBox
    assert combo.count() >= 4 and combo.isEnabled() and combo.currentData() == 'ndb.QP'

    index = combo.findData('ndb.QP_140_146')
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    assert window.options.qpFile == 'ndb.QP_140_146' and window.dataset['qpFile'] == 'ndb.QP_140_146'
    assert 'using ndb.QP_140_146' in system.qpLabel.text()

    system.runChecks()
    assert '⚠' in system.checksLabel.text() and system.checksDetailsButton.isEnabled()
    shown = []
    monkeypatch.setattr(main_window.QMessageBox, 'information', lambda *args: shown.append(args[2]))
    from visual_excitons.gui import options_widget
    monkeypatch.setattr(options_widget.QMessageBox, 'information', lambda *args: shown.append(args[2]))
    system.showChecks()
    assert 'ndb.QP_140_146 (bands 140–146) was computed on this SAVE directory' in shown[-1]


def trickedDataset(tmp_path):
    """BiI3 with BSE files renamed to standard names that are not what they say (as some users do for yambopy)."""
    source = datasetPath(BII3)
    folder = tmp_path / 'tricked'
    (folder / 'diagos').mkdir(parents=True)
    (folder / 'save').symlink_to(source / 'save')
    for n in range(1, 13):
        target = {7: source / 'diagos' / 'ndb.BS_diago_Q30', 9: source / 'qp' / 'ndb.QP'}.get(n, source / 'diagos' / f'ndb.BS_diago_Q{n}')
        if n == 10:
            (folder / 'diagos' / 'ndb.BS_diago_Q10').write_text('not a database')
        else:
            (folder / 'diagos' / f'ndb.BS_diago_Q{n}').symlink_to(target)
    return folder


@pytest.mark.data
def test_every_bse_file_checked(tmp_path):
    folder = trickedDataset(tmp_path)
    files, problems = bseFiles(folder / 'diagos')
    assert len(files) == 12                                    # standard names: taken at their word
    full = checkDataset(str(folder / 'save'), None, str(folder / 'diagos'), files, problems, bseSample=None)
    errors = ' '.join(f['text'] for f in full if f['level'] == ERROR)
    assert 'ndb.BS_diago_Q7: its coordinates are those of Q-point 30' in errors
    assert 'ndb.BS_diago_Q9 is not a BSE database' in errors
    assert 'ndb.BS_diago_Q10 cannot be read' in errors


@pytest.mark.data
def test_check_all_bse_button(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window.openDataset(main_window.findDataset(trickedDataset(tmp_path)))
    system = window.system
    system.runChecks()
    assert system.checkAllBSEButton.isEnabled()

    stages = []
    window.calculations.progressChanged.connect(lambda done, total, stage: stages.append((stage, total)))
    with qtbot.waitSignal(window.calculations.tasks.finished, timeout=60000):
        system.checkAllBSEButton.click()
    assert ('Reading the BSE databases', 12) in stages
    texts = ' '.join(f['text'] for f in system.findings)
    assert 'Q-point 30' in texts and 'ndb.BS_diago_Q9 is not a BSE database' in texts and '✗' in system.checksLabel.text()
    # Kept when the checks run again (e.g. another QP database), until the BSE files change
    system.runChecks()
    assert 'ndb.BS_diago_Q9 is not a BSE database' in ' '.join(f['text'] for f in system.findings)

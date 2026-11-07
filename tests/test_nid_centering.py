"""Front/back group centering, physical PDF placement and native NID controls."""
import json
from pathlib import Path
import pytest
from PIL import Image
from pypdf import PdfReader
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QInputDialog
from app.services.documents import DocumentSession
from app.services.layout import page_size,mm_to_pt,validate_layout
from app.services.pdf import export_pdf


def sides(root):
    session=DocumentSession(root,'nid')
    for name,size,color in [('Front',(700,200),'orange'),('Back',(900,300),'blue')]:
        path=root/(name+'.png');Image.new('RGB',size,color).save(path,dpi=(254,254))
        session.import_image(path,dpi=254,label=name)
    return session


@pytest.mark.parametrize('landscape',[False,True])
@pytest.mark.parametrize('copies,pairs',[(1,1),(3,2),(5,2)])
def test_whole_front_back_batch_centered_on_every_page_with_exact_pdf(tmp_path,landscape,copies,pairs):
    session=sides(tmp_path);originals={p.source:Path(p.source).read_bytes() for p in session.pages}
    job=session.job(dict(center=True,actual_card=True,spacing=7,copies=copies,pairs_per_sheet=pairs,landscape=landscape,align='right',top=0,margin=15))
    assert not validate_layout(job);pw,ph=page_size(job.print_settings)
    for page in range(job.page_count):
        placements=[p for p in job.placements if p.page==page]
        assert (min(p.y for p in placements)+max(p.y+p.height for p in placements))/2==pytest.approx(ph/2)
        assert all(p.x+p.width/2==pytest.approx(pw/2) for p in placements)
        for a,b in zip(placements,placements[1:]):assert b.y-a.y-a.height==pytest.approx(7)
    target=tmp_path/'centered.pdf';export_pdf(job,target);reader=PdfReader(target)
    assert len(reader.pages)==job.page_count
    for page_index,page in enumerate(reader.pages):
        actual=[];matrix=None
        for args,op in page.get_contents().operations:
            if op==b'cm':matrix=[float(v) for v in args]
            elif op==b'Do':actual.append(matrix)
        expected=[p for p in job.placements if p.page==page_index]
        assert len(actual)==len(expected)
        for matrix,p in zip(actual,expected):
            assert matrix==pytest.approx([mm_to_pt(p.width),0,0,mm_to_pt(p.height),mm_to_pt(p.x),mm_to_pt(ph-p.y-p.height)],abs=.0001)
    assert all(Path(path).read_bytes()==data for path,data in originals.items())


@pytest.mark.parametrize('alignment',['left','center','right'])
def test_center_off_preserves_manual_position_and_legacy_settings(tmp_path,alignment):
    session=sides(tmp_path);settings=dict(actual_card=True,top=31,spacing=8,align=alignment)
    for values in (settings,dict(settings,center=False)):
        job=session.job(values);front,back=job.placements
        assert front.y==31 and back.y==pytest.approx(59)
        for p in job.placements:
            assert p.x==pytest.approx(10 if alignment=='left' else 200-p.width if alignment=='right' else (210-p.width)/2)


def test_impossible_centered_batch_fails_without_shrinking_or_detaching(tmp_path):
    session=sides(tmp_path)
    with pytest.raises(ValueError):session.job(dict(center=True,spacing=50,pairs_per_sheet=4,copies=4))


def test_nid_checkbox_controls_group_position_and_saved_session(tmp_path,monkeypatch):
    from app.ui.studio_window import StudioWindow
    from app.ui.hardware_process import HardwareProcess
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'data'));monkeypatch.setattr(HardwareProcess,'start',lambda *a:None)
    app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show();nid=w.shell.nid
    try:
        w.shell.open(nid);app.processEvents();assert nid.center.isChecked()
        nid.advanced_settings.open_settings();app.processEvents()
        assert not nid.align.isEnabled() and not nid.fields['top'].isEnabled()
        fixture=sides(tmp_path)
        # Import real owned copies so the saved session uses valid relative paths.
        for p in fixture.pages:nid.session.import_image(p.source,dpi=254,label=p.label)
        nid.reviewed={id(p) for p in nid.session.pages};job=nid.make_job();pw,ph=page_size(job.print_settings)
        assert (job.placements[0].y+job.placements[-1].y+job.placements[-1].height)/2==pytest.approx(ph/2)
        # Calling the native checkbox signal route enables manual top/alignment.
        nid.center.setFocus();QTest.keyClick(nid.center,Qt.Key_Space);app.processEvents()
        assert not nid.center.isChecked() and nid.align.isEnabled() and nid.fields['top'].isEnabled()
        nid.fields['top'].setValue(25);nid.align.setCurrentText('left');assert nid.make_job().placements[0].y==25
        QTest.keyClick(nid.center,Qt.Key_Space);app.processEvents();assert nid.center.isChecked()
        assert nid.save_session();path=nid.session.root/'session.json';data=json.loads(path.read_text())
        assert data['settings']['center'] is True
        monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:(path.parent.name,True));nid.open_session()
        nid.reviewed={id(p) for p in nid.session.pages};reopened=nid.make_job()
        assert nid.center.isChecked() and not nid.fields['top'].isEnabled()
        assert reopened.placements[0].y==pytest.approx(job.placements[0].y)
    finally:
        w.pool.waitForDone();w.timer.stop();w.invalidate_autosave();nid.dirty=False;w.dirty=False;w.close();app.processEvents()

"""Actual combo/signal regressions for PA-003; all data is disposable."""
import copy
import os
import time
from dataclasses import asdict
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PIL import Image
from pypdf import PdfReader
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from app.models.domain import Job,Photo,Layer
from app.services.layout import page_size,validate_layout,mm_to_pt
from app.services.pdf import export_pdf
from app.ui.studio_window import StudioWindow
from app.ui.canvas import PrintItem


def settle(w):
    end=time.monotonic()+15
    while (w.busy or w.timer.isActive()) and time.monotonic()<end:
        QApplication.processEvents();time.sleep(.01)
    assert not w.busy and not w.timer.isActive()
    QApplication.processEvents()


@pytest.fixture
def session(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=StudioWindow();w.show();app.processEvents()
    errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(str(a[-1])))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Yes)
    source=tmp_path/'synthetic.png';Image.new('RGB',(90,110),'orange').save(source)
    m=w.studio.multi;w.studio.show(m)
    m.add_saved_jobs([Job(photos=[Photo(width=45,height=55,quantity=19,layers=[Layer(str(source))])])])
    settle(w)
    yield w,m,errors
    settle(w);w.dirty=False;w.close();app.processEvents()


def select_paper(m,landscape):
    # Confirm an actual popup selection, including the already-current item.
    m.options.paper.showPopup()
    QTest.keyClick(m.options.paper.view(),Qt.Key_End if landscape else Qt.Key_Home)
    QTest.keyClick(m.options.paper.view(),Qt.Key_Return)


def assert_consistent(w,m,landscape,pages,automatic,dimensions=(45,55),quantity=19,orientation_summary=True):
    settle(w)
    assert m.auto_orientation.isChecked() is automatic
    assert m.options.paper.currentIndex()==int(landscape)
    assert m.options.value()['landscape'] is landscape
    assert m.job.print_settings['landscape'] is landscape
    assert m.job.print_settings['auto_orientation'] is automatic
    assert m.job.page_count==pages and m.pages.count()==pages
    assert m.canvas.sceneRect().width()==pytest.approx(page_size(m.job.print_settings)[0]*3+16)
    assert m.canvas.sceneRect().height()==pytest.approx(page_size(m.job.print_settings)[1]*3+16)
    if orientation_summary:assert ('landscape' if landscape else 'portrait') in m.summary.text()
    assert len(m.job.placements)==quantity
    assert max(r.page for r in m.job.placements)+1==pages
    assert all((r.width,r.height)==dimensions for r in m.job.placements)
    validate_layout(m.job)
    drawn=[item for item in m.canvas.scene().items() if isinstance(item,PrintItem)]
    assert len(drawn)==sum(r.page==m.pages.currentIndex() for r in m.job.placements)
    assert {(item.r.photo_id,item.r.copy) for item in drawn}=={(r.photo_id,r.copy) for r in m.job.placements if r.page==m.pages.currentIndex()}


def test_first_manual_landscape_selection(session):
    w,m,errors=session
    assert_consistent(w,m,False,1,True)
    select_paper(m,True)
    assert_consistent(w,m,True,2,False)
    assert not errors


def test_first_manual_portrait_selection_of_current_item(session):
    w,m,errors=session
    assert_consistent(w,m,False,1,True)
    select_paper(m,False)
    assert_consistent(w,m,False,1,False)
    assert not errors


def click_automatic(m):
    QTest.mouseClick(m.auto_orientation,Qt.LeftButton,pos=QPoint(8,m.auto_orientation.height()//2))


def move_last_copy(w,m):
    m.pages.setCurrentIndex(m.pages.count()-1);settle(w)
    item=max((item for item in m.canvas.scene().items() if isinstance(item,PrintItem)),key=lambda item:item.r.copy)
    before=copy.deepcopy(item.r)
    start=m.canvas.mapFromScene(item.sceneBoundingRect().center());end=start+QPoint(8,0)
    QTest.mousePress(m.canvas.viewport(),Qt.LeftButton,Qt.NoModifier,start)
    QTest.mouseMove(m.canvas.viewport(),end,20)
    QTest.mouseRelease(m.canvas.viewport(),Qt.LeftButton,Qt.NoModifier,end)
    settle(w)
    assert item.r.x>before.x
    assert abs(item.r.y-before.y)<=.25  # Existing drag behavior snaps to 0.5 mm.
    validate_layout(m.job)
    return copy.deepcopy(item.r)


@pytest.mark.parametrize('dimensions,quantity,initial,expected,pages',[
    ((45,55),19,True,False,1),
    ((55,45),19,False,True,1),
    ((45,55),1,True,True,1),
])
def test_automatic_optimization_and_tie_behavior(session,monkeypatch,dimensions,quantity,initial,expected,pages):
    import app.services.print_sessions as service
    w,m,errors=session;source=m.job.photos[0].layers[0].source
    m.new();m.job.photos=[Photo(width=dimensions[0],height=dimensions[1],quantity=quantity,layers=[Layer(source)])]
    m.job.print_settings['landscape']=initial
    calls=[];original=service.auto_layout
    def layout(photos,settings):calls.append(settings['landscape']);return original(photos,settings)
    monkeypatch.setattr(service,'auto_layout',layout)
    m.changed()
    assert calls==[initial,not initial]
    assert_consistent(w,m,expected,pages,True,dimensions,quantity)
    assert not errors


def test_repeated_manual_and_automatic_switching(session,monkeypatch):
    import app.ui.multi_photo_print as module
    w,m,errors=session;calls=[];renders=[];saves=[]
    original_choose=module.choose_orientation;original_render=m.render;original_persist=m.persist
    def choose(photos,settings,automatic=True):
        calls.append((settings['landscape'],automatic));return original_choose(photos,settings,automatic)
    def render(*args):renders.append(True);return original_render(*args)
    def persist():saves.append(True);return original_persist()
    monkeypatch.setattr(module,'choose_orientation',choose)
    monkeypatch.setattr(m,'render',render);monkeypatch.setattr(m,'persist',persist)
    actions=[('manual',True,True,2,False),('manual',False,False,1,False),
             ('auto',None,False,1,True),('manual',True,True,2,False),
             ('auto',None,False,1,True),('manual',False,False,1,False),
             ('manual',True,True,2,False),('manual',False,False,1,False)]
    for kind,value,landscape,pages,automatic in actions:
        calls.clear();renders.clear();saves.clear()
        if kind=='auto':click_automatic(m)
        else:select_paper(m,value)
        assert_consistent(w,m,landscape,pages,automatic)
        assert len(calls)==len(renders)==len(saves)==1
        assert calls[0][1] is automatic
        if not automatic:assert calls[0][0] is landscape
    assert not errors


@pytest.mark.parametrize('mode',['landscape','portrait','automatic'])
def test_saved_session_close_reopen_preserves_mode_and_manual_positions(session,mode):
    w,m,errors=session
    if mode!='automatic':select_paper(m,mode=='landscape')
    settle(w)
    move_last_copy(w,m)
    before=copy.deepcopy(m.job.to_dict());id=m.session_id
    assert m.store.load(id).to_dict()==before
    w.close();QApplication.processEvents()
    reopened=StudioWindow();reopened.show();QApplication.processEvents()
    try:
        restored=reopened.studio.multi;reopened.studio.show(restored);restored.load_session(id);settle(reopened)
        assert restored.job.to_dict()==before
        assert_consistent(reopened,restored,mode=='landscape',2 if mode=='landscape' else 1,mode=='automatic')
        assert restored.store.load(id).to_dict()==before
        for conn in (reopened.db.conn,reopened.tray.conn):
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    finally:settle(reopened);reopened.dirty=False;reopened.close();QApplication.processEvents()
    assert not errors


def test_manual_orientation_quantities_placements_and_pdf(session,tmp_path):
    w,m,errors=session;select_paper(m,True);assert_consistent(w,m,True,2,False)
    original_photo=asdict(m.job.photos[0])
    position=move_last_copy(w,m)
    # Change the real per-composition spin box; a valid existing move must survive.
    qty=m.table.cellWidget(0,2);qty.setValue(20);settle(w)
    assert_consistent(w,m,True,2,False,quantity=20)
    kept=next(r for r in m.job.placements if (r.photo_id,r.copy)==(position.photo_id,position.copy))
    assert (kept.x,kept.y,kept.page)==(position.x,position.y,position.page)
    m.refresh();settle(w);assert (kept.x,kept.y)==(position.x,position.y)
    saved=m.store.load(m.session_id);assert saved.to_dict()==m.job.to_dict()
    pdf=tmp_path/'manual-landscape.pdf';export_pdf(saved,pdf,dpi=100)
    reader=PdfReader(pdf);assert len(reader.pages)==2
    photo_id=m.job.photos[0].id
    for page_index,page in enumerate(reader.pages):
        assert float(page.mediabox.width)==pytest.approx(mm_to_pt(297),abs=.0001)
        assert float(page.mediabox.height)==pytest.approx(mm_to_pt(210),abs=.0001)
        matrices=[];matrix=None
        for args,op in page.get_contents().operations:
            if op==b'cm':matrix=[float(v) for v in args]
            elif op==b'Do':matrices.append(matrix)
        expected=[r for r in saved.placements if r.page==page_index and r.photo_id==photo_id]
        assert len(matrices)==len(expected)
        for matrix,r in zip(matrices,expected):
            assert matrix==pytest.approx([mm_to_pt(45),0,0,mm_to_pt(55),mm_to_pt(r.x),mm_to_pt(210-r.y-55)],abs=.0001)
    assert m.job.photos[0].width==45 and m.job.photos[0].height==55
    assert m.job.photos[0].layers==saved.photos[0].layers
    original_photo['quantity']=20
    assert asdict(m.job.photos[0])==original_photo
    assert not errors


def test_non_paper_settings_preserve_automatic_mode(session):
    w,m,errors=session
    m.options.gap_x.setValue(.4)
    assert_consistent(w,m,False,1,True)
    assert m.job.print_settings['gap_x']==.4
    assert not errors


def test_disabling_automatic_preserves_valid_manual_placements(session,monkeypatch):
    import app.ui.multi_photo_print as module
    w,m,errors=session;move_last_copy(w,m)
    positions=copy.deepcopy(m.job.placements);calls=[];original=module.choose_orientation
    def choose(*a,**k):calls.append(True);return original(*a,**k)
    monkeypatch.setattr(module,'choose_orientation',choose)
    click_automatic(m)
    assert_consistent(w,m,False,1,False,orientation_summary=False)
    assert m.summary.text()=='Manual placements saved. Reopening the session preserves them.'
    assert m.job.placements==positions and not calls
    assert m.store.load(m.session_id).placements==positions
    click_automatic(m)
    assert_consistent(w,m,False,1,True)
    assert len(calls)==1 and not errors


def test_programmatic_refresh_and_load_do_not_recalculate_or_write(session,monkeypatch):
    import app.ui.multi_photo_print as module
    w,m,errors=session;select_paper(m,True);settle(w)
    before=copy.deepcopy(m.job.to_dict());id=m.session_id;calls=[];original=module.choose_orientation
    def choose(*a,**k):calls.append(True);return original(*a,**k)
    monkeypatch.setattr(module,'choose_orientation',choose)
    updates=w.db.conn.total_changes
    m.options.load(m.job.print_settings);m.refresh();settle(w)
    m.load_session(id);settle(w)
    assert not calls and w.db.conn.total_changes==updates
    assert m.job.to_dict()==before and m.auto_orientation.isChecked() is False
    assert not errors

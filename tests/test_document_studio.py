"""Synthetic document/card geometry and real Qt interactions; no device acquisition."""
import os,json,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from pypdf import PdfReader
from app.services.documents import DocumentSession,detect_card,PAPERS
from app.services.hardware import preview_to_scanner,safe_fallback
from app.services.layout import page_size,validate_layout
from app.services.pdf import export_pdf

@pytest.fixture
def app():return QApplication.instance() or QApplication([])

def image(path,size=(600,900),color='white'):
    im=Image.new('RGB',size,color);ImageDraw.Draw(im).text((20,20),'SYNTHETIC SAMPLE - NOT AN ID',fill='black');im.save(path,dpi=(300,300));return path

@pytest.mark.parametrize('paper',list(PAPERS))
@pytest.mark.parametrize('landscape',[False,True])
def test_document_paper_geometry_and_quantities(tmp_path,paper,landscape):
    path=image(tmp_path/'page.png');before=path.read_bytes();session=DocumentSession(tmp_path);session.import_image(path,dpi=300)
    job=session.job(dict(paper=paper,landscape=landscape,copies=5,scale_mode='fit',margin=5));validate_layout(job)
    assert job.page_count==5 and len(job.placements)==5 and len({p.copy for p in job.placements})==5
    assert job.photos[0].width/job.photos[0].height==pytest.approx(600/900)
    pdf=tmp_path/'sheet.pdf';export_pdf(job,pdf);reader=PdfReader(pdf);assert len(reader.pages)==5
    w,h=page_size(job.print_settings)
    assert float(reader.pages[0].mediabox.width)*25.4/72==pytest.approx(w,abs=.0001)
    assert float(reader.pages[0].mediabox.height)*25.4/72==pytest.approx(h,abs=.0001)
    assert path.read_bytes()==before;session.cleanup()

@pytest.mark.parametrize('mode,scale,expected',[('actual',100,50.8),('custom',150,76.2)])
def test_actual_and_custom_physical_size(tmp_path,mode,scale,expected):
    session=DocumentSession(tmp_path);session.import_image(image(tmp_path/'page.png'),dpi=300)
    job=session.job(dict(scale_mode=mode,scale=scale));assert job.photos[0].width==pytest.approx(expected)
    assert job.photos[0].height/job.photos[0].width==pytest.approx(1.5)

def test_large_actual_size_fails_not_silently_fit(tmp_path):
    session=DocumentSession(tmp_path);session.import_image(image(tmp_path/'page.png',(3000,4000)),dpi=100)
    with pytest.raises(ValueError,match='page|margins'):session.job(dict(scale_mode='actual'))
    assert session.job(dict(scale_mode='fit')).placements

def test_document_order_and_one_copy_strategy(tmp_path):
    session=DocumentSession(tmp_path)
    for i,color in enumerate(['red','blue','green']):session.import_image(image(tmp_path/f'{i}.png',color=color),dpi=300,label=f'Page {i}')
    job=session.job(dict(copies=2));assert [p.copy for p in job.placements]==[0,0,0,1,1,1]
    assert [p.page for p in job.placements]==list(range(6)) and sum(p.quantity for p in job.photos)==6

@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('copies',[1,2,5])
def test_nid_front_back_aspect_order_repetition(tmp_path,rotation,copies):
    session=DocumentSession(tmp_path,'nid')
    for side,color in [('Front','orange'),('Back','blue')]:session.import_image(image(tmp_path/f'{side}.png',(1000,630),color),dpi=300,label=side)
    session.pages[1].rotation=rotation;originals={p.source:Path(p.source).read_bytes() for p in session.pages}
    job=session.job(dict(copies=copies,card_width=85.6,card_height=53.98,spacing=10,pairs_per_sheet=1))
    assert job.page_count==copies and len(job.placements)==copies*2
    for i in range(copies):
        front,back=job.placements[i*2:i*2+2];assert front.page==back.page and back.y>=front.y+front.height+9.999
    expected=630/1000 if rotation in (90,270) else 1000/630
    assert job.photos[1].width/job.photos[1].height==pytest.approx(expected)
    assert all(Path(p).read_bytes()==data for p,data in originals.items())

def test_nid_impossible_repetition_rejected(tmp_path):
    session=DocumentSession(tmp_path,'nid')
    for side in ('Front','Back'):session.import_image(image(tmp_path/f'{side}.png',(1000,630)),dpi=300,label=side)
    with pytest.raises(ValueError):session.job(dict(copies=5,pairs_per_sheet=5,card_width=85.6,card_height=53.98))

def test_fictional_card_contour_and_four_corners(tmp_path):
    im=Image.new('RGB',(1400,1000),'white');draw=ImageDraw.Draw(im);draw.polygon([(150,150),(1150,180),(1100,820),(120,770)],fill='#d3dfe9',outline='black',width=5)
    draw.text((300,400),'FICTIONAL TEST CARD - NOT VALID ID',fill='black');points=detect_card(im);assert len(points)==4
    session=DocumentSession(tmp_path,'nid');path=tmp_path/'fictional.png';im.save(path);page=session.import_image(path,dpi=300);page.points=points
    prepared,size=session.prepared(page,{});assert size[0]>size[1] and Image.open(prepared).size==size

def test_session_privacy_cleanup_and_saved_snapshot(tmp_path):
    path=image(tmp_path/'page.png');session=DocumentSession(tmp_path,'nid');page=session.import_image(path,dpi=300,label='Front')
    session.keep=True;session.manifest(dict(card_width=85.6),force=True);before=(session.root/'session.json').read_bytes()
    session.import_image(path,dpi=300,label='Back');assert (session.root/'session.json').read_bytes()==before
    restored=DocumentSession.open(session.root/'session.json');assert len(restored.pages)==1
    assert not session.cleanup() and Path(page.source).exists()
    ephemeral=DocumentSession(tmp_path,'nid');ephemeral.import_image(path);root=ephemeral.root
    assert not ephemeral.cleanup([ephemeral.pages[0].source]);assert ephemeral.cleanup() and not root.exists() and path.exists()

@pytest.mark.parametrize('size,region,points,expected',[
    ((1000,1500),[0,0,200,300],[(100,150),(900,150),(900,1350),(100,1350)],[20,30,160,240]),
    ((500,1000),[10,20,100,200],[(50,100),(450,100),(450,900),(50,900)],[20,40,80,160])])
def test_preview_to_physical_scanner_coordinates(size,region,points,expected):assert preview_to_scanner(points,size,region)==pytest.approx(expected)

@pytest.mark.parametrize('points',[[(-1,0),(10,0),(10,10),(0,10)],[(0,0),(1,0),(1,1),(0,1)],[(0,0)]])
def test_bad_visual_regions_do_not_reach_driver(points):
    with pytest.raises(ValueError):preview_to_scanner(points,(1000,1000),[0,0,210,297])

@pytest.mark.parametrize('started,verified,attempts,allowed',[(False,True,0,True),(True,True,0,False),(False,False,0,False),(False,True,1,False)])
def test_fallback_only_before_acquisition_once(started,verified,attempts,allowed):assert safe_fallback(started,verified,attempts)==allowed

@pytest.fixture
def window(app,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'user'))
    from app.ui.studio_window import StudioWindow
    w=StudioWindow();w.show();app.processEvents();yield w
    w.hardware.shutdown();w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.dirty=False;w.timer.stop();w.invalidate_autosave();w.pool.waitForDone();w.close();app.processEvents()

@pytest.mark.parametrize('size',[(1050,740),(1366,768),(1920,1080)])
@pytest.mark.parametrize('theme',['Dark','Light','System'])
def test_shell_themes_navigation_native_bounds(window,app,size,theme):
    w=window;w.resize(*size);w.shell.set_theme(theme);app.processEvents()
    # Windows constrains oversized native windows to the current monitor; large
    # logical-size coverage also runs in offscreen/high-DPI child processes.
    assert min(size[0],1050)<=w.size().width()<=size[0]
    assert min(size[1],740)<=w.size().height()<=size[1]
    assert w.shell.navigation.count()==13 and w.property('themeMode') in ('Dark','Light')
    w.shell.open(w.shell.copy);app.processEvents();assert w.stack.currentWidget() is w.shell.copy
    assert w.shell.copy.canvas.viewport().width()>=200 and w.shell.copy.canvas.viewport().height()>=200
    w.home();assert w.stack.currentIndex()==0

def test_one_click_connect_then_exactly_one_scan(window,monkeypatch):
    hub=window.hardware;dialog=hub.scan_dialog;hub.scanners=[dict(id='scanner',name='Test scanner',backend='wia',status='Detected')];dialog.update_devices();calls=[]
    monkeypatch.setattr(hub.scan_process,'start',lambda *args:calls.append(args));dialog.scan_now();assert calls[-1][1]['action']=='capabilities'
    dialog.result('capabilities',dict(sources=[dict(id='flatbed',name='Flatbed',width_mm=210,height_mm=297,resolutions=[300,600],colors=['color'],formats=['bmp'])],status='Ready'))
    assert len([r for r in calls if r[1]['action']=='scan'])==1 and calls[-1][1]['dpi']==300

def test_nid_navigation_cancel_preserves_temporary_pixels(window,tmp_path,monkeypatch):
    w=window;workspace=w.shell.nid;path=image(tmp_path/'card.png',(1000,630));workspace.session.import_image(path,label='Front');workspace.dirty=True
    w.stack.setCurrentWidget(workspace);monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Cancel)
    w.home();assert w.stack.currentWidget() is workspace and Path(workspace.session.pages[0].source).is_file()

def test_visual_draw_coordinates_after_zoom(window,app,tmp_path):
    workspace=window.shell.copy;page=workspace.session.import_image(image(tmp_path/'scan.png',(1200,1800)),dpi=300)
    window.shell.open(workspace);workspace.refresh();end=time.monotonic()+10
    while window.busy and time.monotonic()<end:app.processEvents();time.sleep(.01)
    canvas=workspace.canvas;canvas.draw_mode=True;canvas.scale(.8,.8);start=canvas.mapFromScene(200,300);finish=canvas.mapFromScene(700,1000)
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,pos=start);QTest.mouseMove(canvas.viewport(),finish);QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,pos=finish)
    while window.busy and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert page.points and page.points[0][0]==pytest.approx(240,abs=10) and page.points[2][1]==pytest.approx(1200,abs=10)

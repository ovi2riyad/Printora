"""Single bordered prints, requested 42 x 52 default, and pointer-based scan areas."""
import hashlib
import json
import time
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.core.database import Database
from app.models.domain import Photo,Job
from app.services.cropping import detect_photo_regions,extract_region


def test_new_default_and_one_time_migration_preserve_documents_and_later_choices(tmp_path):
    path=tmp_path/'studio.db';db=Database(path)
    assert db.get('default_profile')=='Studio Portrait 42 x 52 mm'
    assert (db.get('portrait_width'),db.get('portrait_height'))==(42,52)
    assert any(p['name']=='Studio Portrait' and (p['width'],p['height'])==(45,55) for p in db.profiles())
    old=Job(photos=[Photo(width=45,height=55)]);db.save_job(old)
    payload=db.conn.execute('SELECT payload FROM jobs WHERE id=?',(old.id,)).fetchone()[0]
    db.set('profile_schema_version',2);db.set('default_profile','Studio Portrait');db.set('portrait_width',45);db.set('portrait_height',55)
    db.conn.close();db=Database(path)
    assert (db.get('portrait_width'),db.get('portrait_height'))==(42,52)
    assert db.conn.execute('SELECT payload FROM jobs WHERE id=?',(old.id,)).fetchone()[0]==payload
    db.set('default_profile','Studio Portrait');db.set('portrait_width',45);db.set('portrait_height',55);db.conn.close()
    db=Database(path);assert db.get('default_profile')=='Studio Portrait' and db.get('portrait_width')==45
    db.conn.close()


def test_new_recipe_name_collision_preserves_custom_recipe(tmp_path):
    path=tmp_path/'studio.db';db=Database(path);name='Studio Portrait 42 x 52 mm'
    custom=dict(next(p for p in db.profiles() if p['name']==name),width=40,height=50,notes='Keep custom settings')
    db.save_profile(custom);db.set('profile_schema_version',2)
    before=db.conn.execute('SELECT payload FROM profiles WHERE name=?',(name,)).fetchone()[0];db.conn.close()
    db=Database(path)
    assert db.conn.execute('SELECT payload FROM profiles WHERE name=?',(name,)).fetchone()[0]==before
    assert db.get('default_profile')==name+' (2)'
    assert (db.get('portrait_width'),db.get('portrait_height'))==(42,52)
    db.conn.close()


def test_supplied_bordered_portrait_has_one_complete_upright_photo():
    path=Path('Demo/IMG.jpg')
    if not path.exists():pytest.skip('Private supplied photo is local only')
    before=hashlib.sha256(path.read_bytes()).digest()
    with Image.open(path) as source:
        regions=detect_photo_regions(source);assert len(regions)==1
        points=regions[0].points
        assert min(x for x,y in points)==pytest.approx(22,abs=2)
        assert min(y for x,y in points)==pytest.approx(25,abs=2)
        assert max(x for x,y in points)==pytest.approx(316,abs=2)
        assert max(y for x,y in points)==pytest.approx(416,abs=2)
        crop=extract_region(source,regions[0]);assert crop.height>crop.width and crop.height>=388
    assert hashlib.sha256(path.read_bytes()).digest()==before


@pytest.mark.parametrize('border',[5,12,24])
def test_single_large_print_rejects_inner_feature_contours(border):
    image=Image.new('RGB',(333,436),'white');draw=ImageDraw.Draw(image)
    draw.rectangle((border,border,332-border,435-border),fill='#2277ac')
    draw.ellipse((90,80,245,280),fill='#ca9374',outline='black',width=3)
    draw.rectangle((80,300,260,400-border),fill='#3a6950')
    regions=detect_photo_regions(image);assert len(regions)==1
    xs=[p[0] for p in regions[0].points];ys=[p[1] for p in regions[0].points]
    assert min(xs)==pytest.approx(border,abs=3) and max(xs)==pytest.approx(332-border,abs=3)
    assert min(ys)==pytest.approx(border,abs=3) and max(ys)==pytest.approx(435-border,abs=3)


@pytest.fixture
def scan(tmp_path,monkeypatch):
    from app.ui.hardware_process import HardwareProcess
    from app.ui.studio_window import StudioWindow
    app=QApplication.instance() or QApplication([])
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'data'))
    calls=[];monkeypatch.setattr(HardwareProcess,'start',lambda self,*args:calls.append(args))
    w=StudioWindow();w.show();app.processEvents();h=w.hardware;d=h.scan_dialog
    h.scanners=[dict(id='SIMULATED',name='Test scanner',backend='wia',status='Simulated')]
    h.populate(h.scanner,h.scanners,'SIMULATED','None');d.update_devices()
    caps=dict(id='flatbed',name='Flatbed',width_mm=230,height_mm=330,resolutions=[100,300,600],colors=['color','gray'])
    w.stack.setCurrentWidget(d);app.processEvents()
    yield w,d,caps,calls
    w.timer.stop();w.pool.waitForDone();app.processEvents();w.invalidate_autosave();w.dirty=False;h.shutdown();w.close();app.processEvents()


def drag(canvas,a,b):
    a=canvas.mapFromScene(QPointF(*a));b=canvas.mapFromScene(QPointF(*b))
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,a)
    QTest.mouseMove(canvas.viewport(),b,25);QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,b)
    QApplication.processEvents()


def test_first_preview_click_connects_then_requests_low_dpi_full_bed(scan):
    w,d,caps,calls=scan
    assert not d.sources and not d.preview_canvas.has_image
    QTest.mouseClick(d.preview_button,Qt.LeftButton)
    assert calls[-1][1]['action']=='capabilities' and d.preview_pending
    d.result('capabilities',dict(sources=[caps],status='Test'))
    request=calls[-1][1];assert request['action']=='scan' and request['dpi']==100 and request['region']==[0,0,230,330]
    assert d.acquisition_preview and not d.preview_button.isEnabled()


def test_repeated_drag_replaces_area_inside_old_selection_and_scans_exactly(scan):
    w,d,caps,calls=scan;d.result('capabilities',dict(sources=[caps],status='Test'))
    d.display_preview(Image.new('RGB',(920,1320),'white'),[0,0,230,330])
    drag(d.preview_canvas,(80,120),(720,1120));first=[b.value() for b in d.region]
    drag(d.preview_canvas,(200,320),(400,600));second=[b.value() for b in d.region]
    assert second==pytest.approx([50,80,50,70],abs=1)
    assert second[2]<first[2] and len(d.preview_canvas.outlines)==1
    QTest.mouseClick(d.scan_button,Qt.LeftButton)
    assert calls[-1][1]['region']==second and calls[-1][1]['dpi']==300


def test_small_area_draw_is_not_discarded_by_cropper_twenty_pixel_threshold(scan):
    w,d,caps,calls=scan;d.result('capabilities',dict(sources=[caps],status='Test'))
    d.display_preview(Image.new('RGB',(920,1320),'white'),[0,0,230,330])
    # Four preview pixels correspond to one physical millimetre.
    d.preview_canvas.scale(5,5);d.preview_canvas.centerOn(200,320)
    drag(d.preview_canvas,(200,320),(208,332))
    assert [b.value() for b in d.region]==pytest.approx([50,80,2,3],abs=.3)


def test_first_preview_handle_resizes_instead_of_starting_new_rectangle(scan):
    w,d,caps,calls=scan;d.result('capabilities',dict(sources=[caps],status='Test'))
    d.display_preview(Image.new('RGB',(920,1320),'white'),[0,0,230,330])
    canvas=d.preview_canvas;handle=canvas.outlines[0].handles[0]
    start=canvas.mapFromScene(handle.scenePos());end=canvas.mapFromScene(QPointF(80,120))
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,start)
    QTest.mouseMove(canvas.viewport(),end,25);QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,end)
    QApplication.processEvents()
    assert [b.value() for b in d.region]==pytest.approx([20,30,210,300],abs=1)
    assert len(canvas.outlines)==1 and canvas.outlines[0].region.points[2]==(920,1320)


def test_full_bed_outline_commits_exact_continuous_edges(scan):
    w,d,caps,calls=scan;d.result('capabilities',dict(sources=[caps],status='Test'))
    d.display_preview(Image.new('RGB',(920,1320),'white'),[0,0,230,330])
    d.preview_canvas.outlines[0].commit()
    assert [b.value() for b in d.region]==[0,0,230,330]


def test_device_discovery_refresh_retains_connected_source_and_preview(scan):
    w,d,caps,calls=scan;d.result('capabilities',dict(sources=[caps],status='Test'))
    image=Image.new('RGB',(460,660),'white');d.display_preview(image,[0,0,230,330]);d.set_region([10,20,30,40])
    w.hardware.twain_devices(dict(devices=[]))
    assert d.sources==[caps] and d.preview_image is image
    assert [b.value() for b in d.region]==[10,20,30,40]


def test_final_cropped_scan_retains_full_bed_for_next_selection(scan,tmp_path,monkeypatch):
    w,d,caps,calls=scan;d.result('capabilities',dict(sources=[caps],status='Test'))
    image=Image.new('RGB',(460,660),'white');d.display_preview(image,[0,0,230,330]);d.set_region([10,20,30,40]);d.scan_now()
    original=tmp_path/'original.bmp';Image.new('RGB',(120,160),'blue').save(original);before=original.read_bytes()
    d.verified(dict(width=120,height=160,format='BMP',original=str(original)))
    assert d.preview_image is image and d.preview_acquired_region==[0,0,230,330]
    assert 'Full-bed preview retained' in d.message.text() and d.completed['original']==str(original)
    assert original.read_bytes()==before


def test_empty_capability_response_is_actionable_and_clears_pending_preview(scan):
    w,d,caps,calls=scan;d.scan_now(preview=True)
    d.result('capabilities',dict(sources=[],status='No source'))
    assert 'no usable scan source' in d.message.text() and not d.pending_scan and not d.preview_pending
    assert not d.scan_button.isEnabled() and d.preview_button.isEnabled()


def test_new_maker_canvas_default_and_legacy_profile_remain_available(scan):
    w,d,caps,calls=scan
    assert w.start_workflow('portrait') and (w.photo.width,w.photo.height)==(42,52)
    assert w.photo.profile=='Studio Portrait 42 x 52 mm'
    w.dirty=False;assert w.start_workflow('joint') and (w.photo.width,w.photo.height)==(55,45)


def test_new_default_pdf_preserves_exact_42_by_52_millimetres(scan,tmp_path):
    from app.models.domain import Layer
    from app.services.layout import auto_layout,mm_to_pt,validate_layout
    from app.services.pdf import export_pdf
    from pypdf import PdfReader
    w,d,caps,calls=scan;w.start_workflow('portrait')
    source=tmp_path/'synthetic.png';Image.new('RGB',(210,260),'orange').save(source)
    w.photo.layers=[Layer(str(source))];w.job.placements=auto_layout(w.job.photos,w.job.print_settings);w.job.page_count=1
    assert not validate_layout(w.job)
    target=tmp_path/'42x52.pdf';export_pdf(w.job,target)
    matrices=[];matrix=None
    for args,op in PdfReader(target).pages[0].get_contents().operations:
        if op==b'cm':matrix=[float(v) for v in args]
        elif op==b'Do':matrices.append(matrix)
    assert len(matrices)==4
    for matrix in matrices:
        assert matrix[0]==pytest.approx(mm_to_pt(42),abs=.0001)
        assert matrix[3]==pytest.approx(mm_to_pt(52),abs=.0001)

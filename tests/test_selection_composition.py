import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PIL import Image,ImageDraw
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.services.cropping import CropTray
from app.services.framing import frame_photo
from app.models.domain import Photo,Layer,Job
from app.ui.photo_library import PhotoLibrary


def test_gallery_real_selection_survives_views_search_and_page(tmp_path):
    app=QApplication.instance() or QApplication([]);tray=CropTray(root=tmp_path/'library')
    a=tray.add('Alice',Image.new('RGB',(20,30),'red'));tray.add('Bob',Image.new('RGB',(20,30),'blue'))
    view=PhotoLibrary(tray);view.resize(800,600);view.show();app.processEvents()
    item=next(view.list.item(i) for i in range(view.list.count()) if view.list.item(i).data(Qt.UserRole)==a.id)
    QTest.mouseClick(view.list.viewport(),Qt.LeftButton,Qt.NoModifier,view.list.visualItemRect(item).center());app.processEvents()
    assert a.id in view.list.selected_ids
    view.search.setText('Bob');view.view.setCurrentIndex(2);view.size.setValue(150);app.processEvents()
    assert [p.id for p in view.chosen()]==[a.id]
    view.search.clear();assert any(view.list.item(i).isSelected() for i in range(view.list.count()))
    view.list.clear_selection();assert not view.chosen();view.close();tray.close()


def test_balanced_margins_roundtrip_and_legacy_framing(tmp_path,monkeypatch):
    p=tmp_path/'person.png';im=Image.new('RGBA',(100,200));ImageDraw.Draw(im).rectangle((20,10,80,190),fill='red');im.save(p)
    monkeypatch.setattr('app.services.framing.detect_faces',lambda im:[])
    photo=Photo(layers=[Layer(str(p),str(p))],composition=dict(top=3,bottom=4,left=5,right=6))
    frame_photo(photo,'balanced')
    from app.services.imaging import render_photo
    rendered=render_photo(photo,254);bg=Image.new('RGB',rendered.size,photo.background)
    from PIL import ImageChops
    bounds=ImageChops.difference(rendered,bg).convert('L').point(lambda v:255 if v>25 else 0).getbbox()
    assert bounds[1]>=29 and bounds[3]<=rendered.height-39
    assert bounds[0]>=49 and bounds[2]<=rendered.width-59
    copy=Job.from_dict(Job(photos=[photo]).to_dict()).photos[0]
    assert copy.composition==photo.composition and copy.layers[0].y==photo.layers[0].y
    photo.composition['bottom']=100
    import pytest
    with pytest.raises(ValueError):frame_photo(photo,'balanced')


def test_library_date_migration_and_bounded_metadata(tmp_path):
    tray=CropTray(root=tmp_path/'library');photo=tray.add('New',Image.new('RGB',(20,20)))
    assert tray.query(date_filter=1)[0].id==photo.id
    with tray.conn:tray.conn.execute('UPDATE photos SET created_at=NULL')
    assert len(tray.query(date_filter=3))==1
    assert tray.query(offset=200)==[]
    tray.close();tray=CropTray(root=tmp_path/'library');assert tray.items[0].serial==photo.serial;tray.close()

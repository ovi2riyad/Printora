import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog,QDialogButtonBox,QPushButton
from app.ui.studio_window import StudioWindow
from app.ui.orders import OrderDialog
from app.models.domain import Job,Photo,Layer


def wait(app,w):
    end=time.monotonic()+40
    while (w.busy or w.timer.isActive()) and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not w.busy and not w.timer.isActive()


def test_mobile_search_order_review_and_reprint_ui(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show();errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda p,t,m:errors.append(m))
    customer=w.studio.customers.save(dict(name='UI Test Customer',mobile='01712345678'))
    source=tmp_path/'source.png';Image.new('RGB',(120,150),'red').save(source)
    job=Job(name='UI order',photos=[Photo(layers=[Layer(str(source))])])
    d=OrderDialog(w.studio,job,w);d.set_customer(customer['id']);d.show();app.processEvents()
    QTest.mouseClick(d.findChild(QDialogButtonBox).button(QDialogButtonBox.Save),Qt.LeftButton);assert d.created
    w.studio.customer_page.refresh();w.studio.show(w.studio.customer_page);w.studio.customer_page.search.setText('01712345678');app.processEvents()
    button=next(b for b in w.studio.customer_page.findChildren(QPushButton) if b.text()=='Orders / reprint');QTest.mouseClick(button,Qt.LeftButton);app.processEvents()
    page=w.studio.order_page;assert page.current_id==d.created['id']
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(tmp_path/'order.pdf'),'PDF'))
    QTest.mouseClick(next(b for b in page.findChildren(QPushButton) if b.text()=='Generate PDF'),Qt.LeftButton);wait(app,w)
    assert (tmp_path/'order.pdf').is_file() and w.studio.orders.get(page.current_id)['status']=='Ready'
    original=page.current_id
    w.studio.customers.save(dict(name='Updated UI customer',mobile='01999999999'),customer['id'])
    page.customer_id=None;page.search.setText('01712345678');page.status.setCurrentText('Ready');app.processEvents()
    QTest.mouseClick(next(b for b in page.findChildren(QPushButton) if b.text()=='Reprint / duplicate'),Qt.LeftButton);app.processEvents()
    assert page.current_id!=original;page.items.cellWidget(0,2).setValue(8)
    assert w.studio.orders.load_job(original).photos[0].quantity==4 and w.studio.orders.load_job(page.current_id).photos[0].quantity==8
    assert not errors;w.dirty=False;w.close()


def test_multi_ui_quantities_reopen_duplicate_and_review(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show()
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Discard)
    source=tmp_path/'person.png';Image.new('RGB',(120,150),'red').save(source)
    source_job=Job(photos=[Photo(layers=[Layer(str(source))]),Photo(width=55,height=45,kind='Joint',layers=[Layer(str(source))])]);w.db.save_job(source_job)
    multi=w.studio.multi;w.studio.show(multi);multi.add_saved_jobs([source_job]);wait(app,w)
    assert len(multi.job.photos)==2 and multi.session_id
    multi.table.cellWidget(0,2).setValue(8);wait(app,w);saved=multi.session_id;copies=[p.quantity for p in multi.job.photos]
    multi.new();multi.load_session(saved);wait(app,w);assert [p.quantity for p in multi.job.photos]==copies
    multi.table.selectRow(0);multi.duplicate();wait(app,w);assert len({p.id for p in multi.job.photos})==3
    multi.table.selectRow(0);multi.edit();wait(app,w);assert w.stack.currentIndex()==1
    w.photo.background='#ff0000';multi.accept_reviewed();wait(app,w);assert multi.job.photos[0].background=='#ff0000'
    assert w.db.load_job(source_job.id).photos[0].background=='#ADD8E6'
    assert w.stack.currentWidget() is multi;w.dirty=False;w.close()

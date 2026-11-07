"""Editable NID sheet preview. Square corner handles reveal the retained scan."""
from pathlib import Path
import copy,uuid,json
from PIL import Image,ImageOps
from PySide6.QtCore import Qt,QPointF,QSize,QRectF
from PySide6.QtGui import QPixmap,QImage,QPainter,QColor,QPen,QPolygonF,QTransform
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QGraphicsView,QGraphicsScene,QGraphicsRectItem,QGraphicsItem,QComboBox,QFileDialog
from PySide6.QtPdf import QPdfDocument
from app.core.database import data_root
from app.services.layout import page_size
from app.services.pdf import export_pdf
from app.services.cropping import order_quad,extract_region,CropRegion
from app.services.imaging import load_image
from app.ui.canvas import pixmap
from app.services.export_safety import check_export_target
from app.services.user_folders import dialog_output


class CardCorner(QGraphicsRectItem):
    def __init__(self,owner,side,index,point):
        super().__init__(-5,-5,10,10);self.owner=owner;self.side=side;self.index=index
        self.setBrush(QColor('white'));self.setPen(QPen(QColor('#2580ff'),2));self.setZValue(30)
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIgnoresTransformations)
        self.setCursor(Qt.SizeAllCursor);self.setPos(point)
    def mousePressEvent(self,event):
        self.start=self.scenePos();self.owner.reveal(self.side);super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if (self.scenePos()-self.start).manhattanLength()>.5:self.owner.commit(self.side)


class NIDView(QGraphicsView):
    """Choose the nearest corner when screen-sized handles overlap at low zoom."""
    def __init__(self,owner):super().__init__();self.owner=owner
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            nearest=None;distance=9*9
            for handles in self.owner.handles.values():
                for handle in handles:
                    handle.setZValue(30)
                    delta=self.mapFromScene(handle.scenePos())-event.position().toPoint();d=delta.x()**2+delta.y()**2
                    if d<distance:nearest=handle;distance=d
            if nearest:nearest.setZValue(40)
        super().mousePressEvent(event)


class NIDPreview(QDialog):
    def __init__(self,workspace):
        super().__init__(workspace.w);self.owner=workspace;self.w=workspace.w;self.job=None;self.path=None;self.generation=0;self.printed=False;self.maps={};self.handles={};self.overlay=None;self.overlay_side=None
        self.setWindowTitle('NID — Adjust corners and print');self.resize(930,820)
        screen=self.screen()
        if screen:self.resize(min(930,screen.availableGeometry().width()-30),min(820,screen.availableGeometry().height()-50))
        layout=QVBoxLayout(self);heading=QLabel('Front + Back · PDF preview');heading.setObjectName('title');layout.addWidget(heading)
        hint=QLabel('Drag the four square dots on either side to adjust its crop. Press a dot to reveal the original scan transparently.');hint.setWordWrap(True);layout.addWidget(hint)
        bar=QHBoxLayout();self.pages=QComboBox();self.pages.currentIndexChanged.connect(self.display);bar.addWidget(self.pages)
        fit=QPushButton('Fit page');fit.clicked.connect(lambda:self.view.fitInView(self.view.sceneRect(),Qt.KeepAspectRatio));bar.addWidget(fit)
        self.settings=QPushButton('Settings');self.settings.clicked.connect(self.open_settings);bar.addWidget(self.settings);bar.addStretch()
        self.save_button=QPushButton('Save PDF');self.save_button.clicked.connect(self.save_pdf);bar.addWidget(self.save_button)
        self.print_button=QPushButton('Print');self.print_button.setObjectName('primary');self.print_button.clicked.connect(self.print_pdf);self.print_button.setEnabled(False);bar.addWidget(self.print_button);layout.addLayout(bar)
        self.view=NIDView(self);self.view.setScene(QGraphicsScene(self.view));self.view.setRenderHint(QPainter.Antialiasing);layout.addWidget(self.view,1)
        self.status=QLabel('Preparing PDF…');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.document=QPdfDocument(self);self.folder=workspace.session.root/'previews'/uuid.uuid4().hex;self.folder.mkdir(parents=True,exist_ok=False)
        self.sources={};self.resize_pending=False
        self.snapshot=None
        self.finished.connect(self.preview_closed)
    def preview_closed(self,*_):self.generation+=1;self.document.close()
    def state(self):
        return json.dumps(dict(settings=self.owner.settings(),pages=[dict(source=p.source,points=p.points,rotation=p.rotation,dpi=p.dpi) for p in self.owner.session.pages]),sort_keys=True)
    def open_settings(self):self.owner.advanced_settings.open_settings()
    def rebuild(self,rollback=None,print_after=False,save_after=False):
        if self.w.busy:return
        self.generation+=1;generation=self.generation;self.print_button.setEnabled(False);self.save_button.setEnabled(False)
        session=copy.copy(self.owner.session);session.pages=copy.deepcopy(session.pages);settings=self.owner.settings();snapshot=self.state();path=self.folder/('preview-'+uuid.uuid4().hex+'.pdf')
        self.status.setText('Updating the PDF…')
        def work():
            job=session.job(settings);export_pdf(job,path);sources={}
            for index,page in enumerate(session.pages):
                image=load_image(page.source,1500)
                with Image.open(page.source) as original:size=ImageOps.exif_transpose(original).size
                points=page.points or [(0,0),(size[0]-1,0),(size[0]-1,size[1]-1),(0,size[1]-1)]
                sources[index]=(image,size,[(float(x),float(y)) for x,y in order_quad(points)],page.rotation)
            return job,sources
        def ready(result):
            if generation!=self.generation:return
            self.job,self.sources=result;self.path=path;self.snapshot=snapshot;self.document.close()
            if self.document.load(str(path))!=QPdfDocument.Error.None_:failed('PDF preview could not be loaded');return
            page=self.pages.currentIndex();self.pages.blockSignals(True);self.pages.clear();self.pages.addItems([f'Page {i+1}' for i in range(self.job.page_count)]);self.pages.setCurrentIndex(max(0,min(page,self.job.page_count-1)));self.pages.blockSignals(False)
            self.printed=False;self.print_button.setEnabled(True);self.save_button.setEnabled(True);self.display();self.status.setText('PDF ready. Check both sides, then Print. Square dots adjust the crop; original files stay unchanged.')
            if print_after:self.print_pdf()
            elif save_after:self.save_pdf()
        def failed(error):
            if rollback:rollback()
            self.status.setText('Could not update this crop: '+str(error)+'. The previous valid PDF is retained.')
            self.print_button.setEnabled(self.job is not None and not self.printed);self.save_button.setEnabled(self.job is not None)
            if self.job:self.display()
        self.w.run(work,ready,failed)
    def display(self,*_):
        if not self.job or not self.path:return
        scene=self.view.scene();scene.clear();self.maps={};self.handles={};self.overlay=None;self.overlay_side=None
        pw,ph=page_size(self.job.print_settings);W,H=round(pw*3),round(ph*3)
        image=self.document.render(max(0,self.pages.currentIndex()),QSize(W,H));paper=QImage(W,H,QImage.Format_RGB32);paper.fill(QColor('white'));painter=QPainter(paper);painter.drawImage(0,0,image);painter.end()
        scene.addPixmap(QPixmap.fromImage(paper));self.view.setSceneRect(0,0,W,H)
        # Each source side has one editable set of four handles, even if copies repeat.
        placements=[p for p in self.job.placements if p.page==max(0,self.pages.currentIndex())]
        for side,photo in enumerate(self.job.photos):
            placement=next((p for p in placements if p.photo_id==photo.id),None)
            if placement is None:continue
            image,size,points,rotation=self.sources[side];sx,sy=image.width/size[0],image.height/size[1]
            source=QPolygonF([QPointF(x*sx,y*sy) for x,y in points])
            x,y=placement.x*W/pw,placement.y*H/ph;w,h=placement.width*W/pw,placement.height*H/ph
            corners=[QPointF(x,y),QPointF(x+w,y),QPointF(x+w,y+h),QPointF(x,y+h)]
            turns=int(rotation//90)%4;dest=QPolygonF([corners[(i+turns)%4] for i in range(4)])
            transform=QTransform();ok=QTransform.quadToQuad(source,dest,transform)
            inverse,invertible=transform.inverted()
            if not ok or not invertible:continue
            self.maps[side]=(transform,inverse,sx,sy);self.handles[side]=[]
            for index,point in enumerate(dest):
                handle=CardCorner(self,side,index,point);scene.addItem(handle);self.handles[side].append(handle)
        self.view.fitInView(self.view.sceneRect(),Qt.KeepAspectRatio)
    def reveal(self,side):
        if side not in self.maps:return
        if self.overlay is not None:self.view.scene().removeItem(self.overlay)
        image=self.sources[side][0];self.overlay=self.view.scene().addPixmap(pixmap(image));self.overlay.setTransform(self.maps[side][0]);self.overlay.setOpacity(.35);self.overlay.setZValue(10);self.overlay.setAcceptedMouseButtons(Qt.NoButton);self.overlay_side=side
        self.status.setText('Original scan overlay — screen only. Drag a square corner to adjust the crop; the PDF contains the cropped card only.')
    def commit(self,side):
        if self.w.busy or side not in self.maps:return
        transform,inverse,sx,sy=self.maps[side];image,size,_,_=self.sources[side]
        points=[]
        for handle in self.handles[side]:
            point=inverse.map(handle.scenePos());points.append((max(0,min(size[0]-1,point.x()/sx)),max(0,min(size[1]-1,point.y()/sy))))
        try:
            # Validate convexity/minimum crop size on the bounded source preview.
            extract_region(image,CropRegion([(x*sx,y*sy) for x,y in points]))
        except ValueError as error:self.status.setText(str(error));self.display();return
        page=self.owner.session.pages[side];old=copy.deepcopy(page.points);page.points=points;self.owner.reviewed.add(id(page));self.owner.dirty=True
        def rollback():page.points=old
        self.rebuild(rollback)
    def print_pdf(self):
        if not self.job or self.w.busy or self.printed:return
        if self.snapshot!=self.state():self.rebuild(print_after=True);return
        accepted=self.w.hardware.print_job(self.job,direct=True,driver_color='gray' if self.owner.color.currentText() in ('gray','mono') else 'color',printer_id=self.owner.printer.currentData())
        if accepted is not False:
            self.printed=True;self.print_button.setEnabled(False);self.status.setText('Print requested. Check the printer output; do not submit the same sheet twice.')
        else:self.status.setText('Print could not start. Check the active print request and printer settings, then retry explicitly.')
    def save_pdf(self):
        if not self.job or self.w.busy:return
        if self.snapshot!=self.state():self.rebuild(save_after=True);return
        path,_=QFileDialog.getSaveFileName(self,'Save reviewed NID PDF',dialog_output(self.w.db,'card-copy.pdf',self.w.notify),'PDF (*.pdf)')
        if not path:return
        try:
            if Path(path).suffix.lower()!='.pdf':raise ValueError('Choose a .pdf filename')
            target=check_export_target(path,data_root(),self.w.db.conn,[p.source for p in self.owner.session.pages]+self.owner.session.input_paths)
        except ValueError as error:self.status.setText(str(error));return
        self.w.run(lambda:export_pdf(self.job,target),lambda _:self.status.setText('PDF saved. Originals unchanged.'))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'view'):self.view.fitInView(self.view.sceneRect(),Qt.KeepAspectRatio)

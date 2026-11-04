"""Sheet/phone cropping workspace and the shared session-photo picker."""
import copy
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt,Signal,QRectF,QPointF,QSize
from PySide6.QtGui import QColor,QPen,QPolygonF,QPainter
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QListWidget,QListWidgetItem,QAbstractItemView,QGraphicsView,QGraphicsScene,QGraphicsItem,QGraphicsPolygonItem,QGraphicsEllipseItem,QGraphicsSimpleTextItem,QDialog,QDialogButtonBox,QFileDialog,QLineEdit,QInputDialog)
from app.services.imaging import load_image,import_info
from app.services.cropping import CropRegion,detect_photo_regions,extract_region,orient_portrait
from app.ui.canvas import pixmap

class Corner(QGraphicsEllipseItem):
    def __init__(self,parent,index,radius):
        super().__init__(-radius,-radius,radius*2,radius*2,parent);self.corner_index=index;self.ready=False
        self.setBrush(QColor('#ffffff'));self.setPen(QPen(QColor('#236b5a'),2));self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemSendsGeometryChanges);self.setZValue(5);self.setCursor(Qt.SizeAllCursor)
    def itemChange(self,change,value):
        if change==QGraphicsItem.ItemPositionHasChanged and self.ready:self.parentItem().corner_moved(self.corner_index,value)
        return super().itemChange(change,value)
    def mouseReleaseEvent(self,e):super().mouseReleaseEvent(e);self.parentItem().commit()

class CropOutline(QGraphicsPolygonItem):
    def __init__(self,region,index,radius,selected_callback,changed_callback,bounds):
        super().__init__(QPolygonF([QPointF(x,y) for x,y in region.points]));self.region=region;self.index=index;self.selected_callback=selected_callback;self.changed_callback=changed_callback;self.bounds=bounds;self.updating=False
        pen=QPen(QColor('#236b5a'),2);pen.setCosmetic(True);self.setPen(pen);self.setBrush(QColor(35,107,90,24));self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable);self.setZValue(2);self.handles=[]
        for i,(x,y) in enumerate(region.points):
            handle=Corner(self,i,radius);handle.setPos(x,y);handle.ready=True;handle.hide();self.handles.append(handle)
    def itemChange(self,change,value):
        if change==QGraphicsItem.ItemSelectedHasChanged:
            for h in getattr(self,'handles',[]):h.setVisible(bool(value))
        return super().itemChange(change,value)
    def mousePressEvent(self,e):
        super().mousePressEvent(e);self.selected_callback(self.index)
    def corner_moved(self,index,point):
        if self.updating:return
        polygon=self.polygon();polygon[index]=point;self.setPolygon(polygon)
    def commit(self):
        w,h=self.bounds;points=[self.mapToScene(p) for p in self.polygon()]
        self.region.points=[(max(0,min(w-1,p.x())),max(0,min(h-1,p.y()))) for p in points];self.changed_callback(self.index)
    def mouseReleaseEvent(self,e):super().mouseReleaseEvent(e);self.commit()

class CropCanvas(QGraphicsView):
    selected=Signal(int)
    changed=Signal(int)
    drawn=Signal(object)
    def __init__(self):
        super().__init__();self.setScene(QGraphicsScene(self));self.setRenderHint(QPainter.Antialiasing);self.setMinimumSize(350,400);self.outlines=[];self.drawing=None;self.anchor=None;self.has_image=False;self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
    def display(self,image,regions,selected=0):
        self.scene().clear();self.outlines=[];self.has_image=True;self.anchor=None;self.drawing=None
        preview=image.copy();preview.thumbnail((1400,1400));background=self.scene().addPixmap(pixmap(preview));background.setScale(image.width/preview.width)
        self.setSceneRect(0,0,image.width,image.height);radius=max(image.size)/180
        for i,region in enumerate(regions):
            outline=CropOutline(region,i,radius,self.selected.emit,self.changed.emit,image.size);self.scene().addItem(outline);self.outlines.append(outline)
            text=QGraphicsSimpleTextItem(str(i+1),outline);text.setBrush(QColor('#236b5a'));text.setScale(max(image.size)/700);text.setPos(*region.points[0]);text.setZValue(0);text.setAcceptedMouseButtons(Qt.NoButton)
        self.select_region(selected);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
    def select_region(self,index):
        for i,item in enumerate(self.outlines):item.setSelected(i==index)
    def mousePressEvent(self,e):
        item=self.itemAt(e.position().toPoint())
        if item is not None and isinstance(item.parentItem(),CropOutline) and not isinstance(item,Corner):item=item.parentItem()
        if self.has_image and e.button()==Qt.LeftButton and not isinstance(item,(CropOutline,Corner)):
            self.anchor=self.mapToScene(e.position().toPoint());pen=QPen(QColor('#d48429'),2);pen.setCosmetic(True);self.drawing=self.scene().addRect(QRectF(self.anchor,self.anchor),pen);return
        super().mousePressEvent(e)
    def mouseMoveEvent(self,e):
        if self.drawing is not None:self.drawing.setRect(QRectF(self.anchor,self.mapToScene(e.position().toPoint())).normalized());return
        super().mouseMoveEvent(e)
    def mouseReleaseEvent(self,e):
        if self.drawing is not None:
            rect=self.drawing.rect().intersected(self.sceneRect());self.scene().removeItem(self.drawing);self.drawing=None;self.anchor=None
            if min(rect.width(),rect.height())>=20:self.drawn.emit(CropRegion([(rect.left(),rect.top()),(rect.right(),rect.top()),(rect.right(),rect.bottom()),(rect.left(),rect.bottom())]))
            return
        super().mouseReleaseEvent(e)
    def resizeEvent(self,e):super().resizeEvent(e);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
    def wheelEvent(self,e):self.scale(1.2 if e.angleDelta().y()>0 else 1/1.2,1.2 if e.angleDelta().y()>0 else 1/1.2)
    def mouseDoubleClickEvent(self,e):
        item=self.itemAt(e.position().toPoint())
        if isinstance(item,Corner):item=item.parentItem()
        if isinstance(item,CropOutline):self.fitInView(item.sceneBoundingRect().adjusted(-30,-30,30,30),Qt.KeepAspectRatio);return
        super().mouseDoubleClickEvent(e)

class PreparedPicker(QDialog):
    def __init__(self,tray,count,parent=None):
        super().__init__(parent);self.tray=tray;self.count=count;self.setWindowTitle('Choose prepared photo' if count==1 else 'Choose two prepared photos');self.resize(760,540);layout=QVBoxLayout(self)
        counts=(count,) if isinstance(count,int) else count;self.counts=counts
        layout.addWidget(QLabel('Select one existing joint photo, or two separate portraits.' if len(counts)>1 else f'Select {count} prepared photo'+('s.' if count>1 else '.')))
        self.search=QLineEdit();self.search.setPlaceholderText('Search by serial number or name');self.search.textChanged.connect(self.filter);layout.addWidget(self.search)
        self.list=QListWidget();self.list.setSelectionMode(QAbstractItemView.ExtendedSelection if max(counts)>1 else QAbstractItemView.SingleSelection);self.list.setIconSize(QSize(100,120));layout.addWidget(self.list)
        self.checked=set();self.error=QLabel();layout.addWidget(self.error);buttons=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons);self.list.itemChanged.connect(self.check_changed);self.filter('')
    def chosen(self):
        ids=self.checked or {i.data(Qt.UserRole) for i in self.list.selectedItems()};return [p for p in self.tray.items if p.id in ids]
    def accept(self):
        if len(self.chosen()) not in self.counts:self.error.setText('Choose one combined photo or two portraits.' if len(self.counts)>1 else f'Choose exactly {self.count} photo'+('s.' if self.count>1 else '.'));return
        super().accept()
    def filter(self,text):
        from PySide6.QtGui import QIcon
        matches=[p for p in self.tray.items if text.lower() in p.display_name.lower()];self.list.blockSignals(True);self.list.clear()
        for p in matches[-200:]:
            w,h=p.size;item=QListWidgetItem(QIcon(pixmap(p.thumbnail())),p.display_name+f'   ·   {w} × {h} px');item.setData(Qt.UserRole,p.id)
            if max(self.counts)>1:item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if p.id in self.checked else Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False);self.error.setText(f'{len(self.checked)} checked. Showing up to 200 recent matches; search finds older serials.')
    def check_changed(self,item):
        id=item.data(Qt.UserRole)
        if item.checkState()==Qt.Checked:self.checked.add(id)
        else:self.checked.discard(id)
        self.error.setText(f'{len(self.checked)} checked. '+('Open one combined photo or two portraits.' if len(self.counts)>1 else f'Choose {self.count} photos.'))

class Cropper(QWidget):
    def __init__(self,tray,run,notify,use,parent=None):
        super().__init__(parent);self.tray=tray;self.run=run;self.notify=notify;self.use=use;self.source_paths=[];self.current_image=None;self.current_path='';self.regions=[];self.source_states={};self.updating=False
        self.setStyleSheet('QPushButton {padding:6px 9px;font-size:12px;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);header=QLabel('Cropper');header.setObjectName('title');layout.addWidget(header)
        layout.addWidget(QLabel('Import a scan sheet or camera photo. Separate each person, then keep their crop in the tray.'))
        row=QHBoxLayout();self.button('Import images / scan sheets',self.import_sources,row);self.sources=QComboBox();self.sources.currentIndexChanged.connect(self.select_source);row.addWidget(self.sources,1);self.button('Auto-detect photos',self.detect,row);self.button('Use whole image',self.full_image,row);self.button('Fit sheet',lambda:self.canvas.fitInView(self.canvas.sceneRect(),Qt.KeepAspectRatio),row);layout.addLayout(row)
        body=QHBoxLayout();layout.addLayout(body,1);self.canvas=CropCanvas();self.canvas.selected.connect(self.select_region);self.canvas.changed.connect(self.region_changed);self.canvas.drawn.connect(self.add_region);body.addWidget(self.canvas,1)
        side=QVBoxLayout();side.setSpacing(6);body.addLayout(side);side.addWidget(QLabel('Crop regions · drag corners to adjust'))
        self.region_list=QListWidget();self.region_list.setMaximumHeight(100);self.region_list.setMinimumHeight(60);self.region_list.setFixedWidth(300);self.region_list.currentRowChanged.connect(self.canvas.select_region);side.addWidget(self.region_list)
        row=QHBoxLayout();self.button('Rotate left',lambda:self.rotate(90),row);self.button('Rotate right',lambda:self.rotate(-90),row);self.button('Delete',self.remove_region,row);side.addLayout(row)
        row=QHBoxLayout();self.button('Keep selected crop',self.keep_selected,row);self.button('Keep all crops',self.keep_all,row);side.addLayout(row)
        self.tray_label=QLabel('Saved library · 0 photos');row=QHBoxLayout();row.addWidget(self.tray_label,1);self.button('Rename',self.rename_photo,row);self.button('Remove',self.remove_from_tray,row);side.addLayout(row)
        self.search=QLineEdit();self.search.setPlaceholderText('Find serial number or name');self.search.textChanged.connect(self.filter_tray);side.addWidget(self.search)
        self.tray_list=QListWidget();self.tray_list.setSelectionMode(QAbstractItemView.ExtendedSelection);self.tray_list.setViewMode(QListWidget.IconMode);self.tray_list.setResizeMode(QListWidget.Adjust);self.tray_list.setGridSize(QSize(92,105));self.tray_list.setIconSize(QSize(58,70));side.addWidget(self.tray_list,1)
        row=QHBoxLayout();self.button('Portrait print →',lambda:self.use_selected('portrait'),row);self.button('Joint print →',lambda:self.use_selected('joint'),row);side.addLayout(row)
        self.hint=QLabel('Wheel to zoom; double-click a region to inspect it. Drag an empty area to draw a crop. Imported sources and numbered crops are saved automatically.');self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.restore_sources();self.refresh_tray()
    def restore_sources(self):
        self.source_names={};self.sources.blockSignals(True)
        for serial,name,path in self.tray.sources():
            self.source_names[path]=name
            if path not in self.source_paths:self.source_paths.append(path);self.sources.addItem(f'S{serial:06d} · {name}')
        self.sources.blockSignals(False)
    def button(self,text,fn,layout):
        b=QPushButton(text);b.clicked.connect(fn);layout.addWidget(b);return b
    def import_sources(self,checked=False,paths=None):
        if paths is None:paths,_=QFileDialog.getOpenFileNames(self,'Import scan sheets or phone photographs','','Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)')
        if not paths:return
        def read():
            valid=[];errors=[]
            for path in paths:
                try:valid.append(self.tray.import_source(import_info(path)[0]))
                except Exception as e:errors.append(f'{Path(path).name}: {e}')
            return valid,errors
        def done(result):
            self.restore_sources()
            self.sources.blockSignals(True)
            for path in result[0]:
                if path not in self.source_paths:self.source_paths.append(path);self.sources.addItem(Path(path).name)
            self.sources.blockSignals(False)
            if result[1]:self.notify('Some imports failed: '+'; '.join(result[1]))
            if result[0]:self.sources.blockSignals(True);index=self.source_paths.index(result[0][0]);self.sources.setCurrentIndex(index);self.sources.blockSignals(False);self.select_source(index)
        self.run(read,done)
    def select_source(self,index):
        if not 0<=index<len(self.source_paths):return
        if self.current_path:self.source_states[self.current_path]=copy.deepcopy(self.regions)
        path=self.source_paths[index];stored=self.source_states.get(path,self.tray.load_regions(path))
        self.notify('Loading source and looking for separate photographs…')
        def load():
            image=load_image(path,10000);regions=copy.deepcopy(stored) if stored is not None else detect_photo_regions(image)
            if not regions:regions=[CropRegion([(0,0),(image.width-1,0),(image.width-1,image.height-1),(0,image.height-1)])]
            return image,regions
        def done(result):
            self.current_path=path;self.current_image,self.regions=result;self.refresh_regions();self.notify(f'{len(self.regions)} crop regions found. Check their edges before keeping them.')
        self.run(load,done)
    def refresh_regions(self,selected=0):
        if self.current_path:self.tray.save_regions(self.current_path,self.regions)
        self.region_list.blockSignals(True);self.region_list.clear();self.region_list.addItems([f'Crop {i+1}'+(f' · rotate {r.rotation}°' if r.rotation else '') for i,r in enumerate(self.regions)]);self.region_list.setCurrentRow(min(selected,len(self.regions)-1));self.region_list.blockSignals(False)
        if self.current_image:self.canvas.display(self.current_image,self.regions,self.region_list.currentRow())
    def select_region(self,index):self.region_list.setCurrentRow(index)
    def region_changed(self,index):
        if self.current_path:self.source_states[self.current_path]=copy.deepcopy(self.regions);self.tray.save_regions(self.current_path,self.regions)
        self.hint.setText(f'Crop {index+1} adjusted. Keep it when the corners match the photograph.')
    def add_region(self,region):self.regions.append(region);self.refresh_regions(len(self.regions)-1)
    def remove_region(self):
        i=self.region_list.currentRow()
        if i>=0:self.regions.pop(i);self.refresh_regions(max(0,i-1))
    def rotate(self,angle):
        i=self.region_list.currentRow()
        if i>=0:self.regions[i].rotation=(self.regions[i].rotation+angle)%360;self.refresh_regions(i)
    def full_image(self):
        if self.current_image:
            w,h=self.current_image.size;self.add_region(CropRegion([(0,0),(w-1,0),(w-1,h-1),(0,h-1)]))
    def detect(self):
        if not self.current_image:return
        image=self.current_image
        def done(regions):self.regions=regions;self.refresh_regions();self.notify(f'{len(regions)} regions detected. Draw any missing crops manually.')
        self.run(lambda:detect_photo_regions(image),done)
    def keep_selected(self):
        i=self.region_list.currentRow()
        if i>=0:self.keep([i])
    def keep_all(self):self.keep(list(range(len(self.regions))))
    def keep(self,indexes):
        if not indexes or not self.current_image:return
        image=self.current_image;path=self.current_path;regions=[(i,copy.deepcopy(self.regions[i])) for i in indexes]
        self.notify('Extracting crops and checking upright orientation…')
        def process():
            result=[]
            for i,region in regions:
                crop=extract_region(image,region)
                if not region.rotation:crop,_=orient_portrait(crop)
                result.append((f'{Path(self.source_names.get(path,path)).stem} · crop {i+1}',crop))
            if self.tray.conn:
                for name,crop in result:self.tray.add(name,crop,path)
                return len(result)
            return result
        def done(rows):
            if isinstance(rows,int):self.refresh_tray();self.notify(f'{rows} numbered photos saved to your library.');return
            total=sum(p.image.width*p.image.height for p in self.tray.items)+sum(im.width*im.height for _,im in rows)
            if total>self.tray.max_pixels:raise ValueError('The crop tray is full. Remove unused crops first.')
            for name,image in rows:self.tray.add(name,image,path)
            self.refresh_tray();self.notify(f'{len(rows)} crops kept. Choose one for portrait print or two for joint print.')
        self.run(process,done)
    def refresh_tray(self):
        self.tray_label.setText(f'Saved library · {len(self.tray.items)} photos');self.filter_tray(self.search.text())
    def filter_tray(self,text):
        from PySide6.QtGui import QIcon
        self.tray_list.clear();matches=[p for p in self.tray.items if text.lower() in p.display_name.lower()]
        for p in matches[-200:]:
            item=QListWidgetItem(QIcon(pixmap(p.thumbnail((58,70)))),p.display_name);item.setData(Qt.UserRole,p.id);item.setToolTip(p.display_name);self.tray_list.addItem(item)
    def rename_photo(self):
        selected=self.tray_list.selectedItems()
        if len(selected)!=1:self.notify('Select one library photo to rename.');return
        item=next(p for p in self.tray.items if p.id==selected[0].data(Qt.UserRole));name,ok=QInputDialog.getText(self,'Rename photo','Photo name',text=item.name)
        if ok and name.strip():self.tray.rename(item,name);self.refresh_tray()
    def remove_from_tray(self):self.tray.remove({i.data(Qt.UserRole) for i in self.tray_list.selectedItems()});self.refresh_tray()
    def use_selected(self,mode):
        ids={i.data(Qt.UserRole) for i in self.tray_list.selectedItems()};items=[p for p in self.tray.items if p.id in ids];count=1 if mode=='portrait' else 2
        if len(items) not in ((1,) if mode=='portrait' else (1,2)):self.notify('Select one portrait, or one combined/two separate photos for joint print.');return
        self.use(mode,items)

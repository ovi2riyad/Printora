"""Sheet/phone cropping workspace and the shared session-photo picker."""
from app.services.user_folders import dialog_folder,dialog_output
import copy
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt,Signal,QRectF,QPointF,QSize
from PySide6.QtGui import QColor,QPen,QPolygonF,QPainter
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QListWidget,QListWidgetItem,QAbstractItemView,QGraphicsView,QGraphicsScene,QGraphicsItem,QGraphicsPolygonItem,QGraphicsEllipseItem,QGraphicsSimpleTextItem,QDialog,QDialogButtonBox,QFileDialog,QLineEdit,QInputDialog,QTabWidget)
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
        for i in range(4):
            first,second=QPointF(*region.points[i]),QPointF(*region.points[(i+1)%4]);handle=Corner(self,i+4,radius*.8);handle.setPos((first+second)/2);handle.ready=True;handle.hide();self.handles.append(handle)
    def itemChange(self,change,value):
        if change==QGraphicsItem.ItemSelectedHasChanged:
            for h in getattr(self,'handles',[]):h.setVisible(bool(value))
        return super().itemChange(change,value)
    def mousePressEvent(self,e):
        super().mousePressEvent(e);self.selected_callback(self.index)
    def corner_moved(self,index,point):
        if self.updating:return
        polygon=self.polygon()
        if getattr(self,'rectangular',False):
            if index<4:
                rect=QRectF(polygon[(index+2)%4],point).normalized()
            else:
                rect=polygon.boundingRect()
                if index==4:rect.setTop(point.y())
                elif index==5:rect.setRight(point.x())
                elif index==6:rect.setBottom(point.y())
                else:rect.setLeft(point.x())
                rect=rect.normalized()
            polygon=QPolygonF([rect.topLeft(),rect.topRight(),rect.bottomRight(),rect.bottomLeft()])
        elif index<4:polygon[index]=point
        else:
            first=index-4;second=(first+1)%4;delta=point-(polygon[first]+polygon[second])/2;polygon[first]+=delta;polygon[second]+=delta
        self.setPolygon(polygon);self.updating=True
        for i,h in enumerate(self.handles):h.setPos(polygon[i] if i<4 else (polygon[i-4]+polygon[(i-3)%4])/2)
        self.updating=False
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
        if getattr(self,'pan_mode',False):super().mousePressEvent(e);return
        item=self.itemAt(e.position().toPoint())
        if item is not None and isinstance(item.parentItem(),CropOutline) and not isinstance(item,Corner):item=item.parentItem()
        if self.has_image and e.button()==Qt.LeftButton and (getattr(self,'draw_mode',False) or not isinstance(item,(CropOutline,Corner))):
            self.anchor=self.mapToScene(e.position().toPoint());pen=QPen(QColor('#d48429'),2);pen.setCosmetic(True);self.drawing=self.scene().addRect(QRectF(self.anchor,self.anchor),pen);return
        super().mousePressEvent(e)
    def mouseMoveEvent(self,e):
        if self.drawing is not None:self.drawing.setRect(QRectF(self.anchor,self.mapToScene(e.position().toPoint())).normalized());return
        super().mouseMoveEvent(e)
    def mouseReleaseEvent(self,e):
        if self.drawing is not None:
            self.draw_mode=False
            rect=self.drawing.rect().intersected(self.sceneRect());self.scene().removeItem(self.drawing);self.drawing=None;self.anchor=None
            if min(rect.width(),rect.height())>=getattr(self,'minimum_draw_pixels',20):self.drawn.emit(CropRegion([(rect.left(),rect.top()),(rect.right(),rect.top()),(rect.right(),rect.bottom()),(rect.left(),rect.bottom())]))
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
        from app.ui.photo_library import PhotoLibrary
        self.gallery=PhotoLibrary(tray,maximum=max(counts));layout.addWidget(self.gallery)
        self.search=self.gallery.search;self.list=self.gallery.list;self.checked=self.list.selected_ids
        self.error=QLabel();layout.addWidget(self.error);buttons=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def chosen(self):
        return self.gallery.chosen()
    def accept(self):
        if len(self.chosen()) not in self.counts:self.error.setText('Choose one combined photo or two portraits.' if len(self.counts)>1 else f'Choose exactly {self.count} photo'+('s.' if self.count>1 else '.'));return
        super().accept()
    def filter(self,text):
        self.search.setText(text);self.gallery.refresh()
    def check_changed(self,item):
        self.list.check_changed(item)

class Cropper(QWidget):
    def __init__(self,tray,run,notify,use,parent=None,db=None):
        super().__init__(parent);self.tray=tray;self.run=run;self.notify=notify;self.use=use;self.source_paths=[];self.current_image=None;self.current_path='';self.regions=[];self.source_states={};self.updating=False;self.crop_undo={};self.crop_redo={};self.last_regions=[]
        self.on_sources_imported=None;self.on_crops_saved=None;self.settings_db=db
        self.setStyleSheet('QPushButton {padding:6px 9px;font-size:12px;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);header=QLabel('Cropper');header.setObjectName('title');layout.addWidget(header)
        layout.addWidget(QLabel('Import a scan sheet or camera photo. Separate each person, then keep their crop in the tray.'))
        row=QHBoxLayout();self.button('Import images / scan sheets',self.import_sources,row);self.sources=QComboBox();self.sources.currentIndexChanged.connect(self.select_source);row.addWidget(self.sources,1);self.button('Auto-detect photos',self.detect,row);self.button('Use whole image',self.full_image,row);self.button('Fit sheet',lambda:self.canvas.fitInView(self.canvas.sceneRect(),Qt.KeepAspectRatio),row);layout.addLayout(row)
        body=QHBoxLayout();layout.addLayout(body,1);self.canvas=CropCanvas();self.canvas.selected.connect(self.select_region);self.canvas.changed.connect(self.region_changed);self.canvas.drawn.connect(self.add_region)
        self.side_tabs=QTabWidget();region_panel=QWidget();self.side_tabs.addTab(region_panel,'Crop regions');side=QVBoxLayout(region_panel);side.setSpacing(8);side.addWidget(QLabel('Move corners or edge handles to refine a crop.'))
        from app.ui.panels import AdaptivePanel,splitter
        self.properties_panel=AdaptivePanel(self.side_tabs,db,'cropper','Crop / Library',[('Crop regions','tools',lambda:self.side_tabs.setCurrentIndex(0)),('Saved library','library',lambda:self.side_tabs.setCurrentIndex(1))]);body.addWidget(splitter(self.canvas,self.properties_panel))
        self.region_list=QListWidget();self.region_list.setMinimumHeight(100);self.region_list.currentRowChanged.connect(self.canvas.select_region);side.addWidget(self.region_list,1)
        row=QHBoxLayout();self.button('Rotate left',lambda:self.rotate(90),row);self.button('Rotate right',lambda:self.rotate(-90),row);self.button('Delete',self.remove_region,row);side.addLayout(row)
        row=QHBoxLayout();self.button('Undo crop',self.undo_crop,row);self.button('Redo crop',self.redo_crop,row);self.button('Preview crop',self.preview_crop,row);side.addLayout(row)
        row=QHBoxLayout();self.button('Keep selected crop',self.keep_selected,row);self.button('Keep all crops',self.keep_all,row);side.addLayout(row)
        library_panel=QWidget();self.side_tabs.addTab(library_panel,'Saved library');side=QVBoxLayout(library_panel);side.setSpacing(8)
        self.tray_label=QLabel('Saved library · 0 photos');row=QHBoxLayout();row.addWidget(self.tray_label,1);self.button('Rename',self.rename_photo,row);self.button('Remove',self.remove_from_tray,row);side.addLayout(row)
        self.search=QLineEdit();self.search.setPlaceholderText('Find serial number or name');self.search.textChanged.connect(self.filter_tray);side.addWidget(self.search)
        row=QHBoxLayout();self.sort=QComboBox();self.sort.addItems(['Newest first','Oldest first','Serial ascending']);self.sort.currentIndexChanged.connect(lambda:self.filter_tray(self.search.text()));row.addWidget(self.sort);self.kind_filter=QComboBox();self.kind_filter.addItems(['All','Individual','Joint']);self.kind_filter.currentTextChanged.connect(lambda:self.filter_tray(self.search.text()));row.addWidget(self.kind_filter);side.addLayout(row)
        row=QHBoxLayout();self.deleted=QComboBox();self.deleted.addItems(['Available photos','Removed photos']);self.deleted.currentIndexChanged.connect(lambda:self.filter_tray(self.search.text()));row.addWidget(self.deleted);self.button('Restore selected',self.restore_selected,row);side.addLayout(row)
        from app.ui.selection import PhotoSelectionList
        self.tray_list=PhotoSelectionList();self.tray_list.setViewMode(QListWidget.IconMode);self.tray_list.setResizeMode(QListWidget.Adjust);self.tray_list.setGridSize(QSize(130,155));self.tray_list.setIconSize(QSize(94,110));side.addWidget(self.tray_list,1)
        self.selection_count=QLabel();self.selection_count.setWordWrap(True);side.addWidget(self.selection_count)
        self.tray_list.selection_updated.connect(self.selection_summary)
        select_row=QHBoxLayout();self.button('Select visible',self.tray_list.select_visible,select_row);self.button('Clear',self.tray_list.clear_selection,select_row);side.addLayout(select_row)
        self.tray_list.itemDoubleClicked.connect(lambda _:self.preview_library())
        row=QHBoxLayout();self.button('Mark individual',lambda:self.mark_kind('Individual'),row);self.button('Mark joint',lambda:self.mark_kind('Joint'),row);side.addLayout(row)
        row=QHBoxLayout();self.button('Portrait print →',lambda:self.use_selected('portrait'),row);self.button('Joint print →',lambda:self.use_selected('joint'),row);side.addLayout(row)
        self.hint=QLabel('Wheel to zoom; double-click a region to inspect it. Drag an empty area to draw a crop. Imported sources and numbered crops are saved automatically.');self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.restore_sources();self.refresh_tray()
    def restore_sources(self):
        aliases=getattr(self.tray,'source_aliases',{})
        if aliases:
            self.current_path=aliases.get(self.current_path,self.current_path)
            for name in ('source_states','crop_undo','crop_redo'):
                state=getattr(self,name,{})
                for old,new in aliases.items():
                    if old in state:state[new]=state.pop(old)
            self.source_paths=[aliases.get(p,p) for p in self.source_paths]
        self.source_names={};self.sources.blockSignals(True)
        for serial,name,path in self.tray.sources():
            self.source_names[path]=name
            if path not in self.source_paths:self.source_paths.append(path);self.sources.addItem(f'S{serial:06d} · {name}')
        self.sources.blockSignals(False)
    def button(self,text,fn,layout):
        b=QPushButton(text);b.clicked.connect(fn);layout.addWidget(b);return b
    def import_sources(self,checked=False,paths=None):
        if paths is None:paths,_=QFileDialog.getOpenFileNames(self,'Import scan sheets or phone photographs',dialog_folder(self.settings_db,'input',self.notify),'Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)')
        if not paths:return
        def read():
            valid=[];errors=[]
            for path in paths:
                try:valid.append(self.tray.import_source(import_info(path)[0]))
                except Exception as e:errors.append(f'{Path(path).name}: {e}')
            return valid,errors
        def done(result):
            self.restore_sources()
            if self.on_sources_imported:self.on_sources_imported(result[0])
            self.sources.blockSignals(True)
            for path in result[0]:
                if path not in self.source_paths:self.source_paths.append(path);self.sources.addItem(Path(path).name)
            self.sources.blockSignals(False)
            if not hasattr(self,'import_summary'):
                self.import_summary=QLabel();self.import_summary.setWordWrap(True);self.layout().addWidget(self.import_summary)
            self.import_summary.setText(f'{len(result[0])} imported; {len(result[1])} failed.'+('\n'+'\n'.join(result[1]) if result[1] else ''))
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
            self.current_path=path;self.current_image,self.regions=result;self.refresh_regions();self.side_tabs.setCurrentIndex(0);self.notify(f'{len(self.regions)} crop regions found. Check their edges before keeping them.')
        self.run(load,done)
    def refresh_regions(self,selected=0):
        if self.current_path:self.tray.save_regions(self.current_path,self.regions);self.source_states[self.current_path]=copy.deepcopy(self.regions)
        self.last_regions=copy.deepcopy(self.regions)
        self.region_list.blockSignals(True);self.region_list.clear();self.region_list.addItems([f'Crop {i+1}'+(f' · rotate {r.rotation}°' if r.rotation else '') for i,r in enumerate(self.regions)]);self.region_list.setCurrentRow(min(selected,len(self.regions)-1));self.region_list.blockSignals(False)
        if self.current_image:self.canvas.display(self.current_image,self.regions,self.region_list.currentRow())
    def select_region(self,index):self.region_list.setCurrentRow(index)
    def region_changed(self,index):
        self.crop_checkpoint(self.last_regions)
        if self.current_path:self.source_states[self.current_path]=copy.deepcopy(self.regions);self.tray.save_regions(self.current_path,self.regions)
        self.last_regions=copy.deepcopy(self.regions)
        self.hint.setText(f'Crop {index+1} adjusted. Keep it when the corners match the photograph.')
    def crop_checkpoint(self,regions=None):
        if not self.current_path:return
        stack=self.crop_undo.setdefault(self.current_path,[]);stack.append(copy.deepcopy(self.regions if regions is None else regions));del stack[:-50];self.crop_redo[self.current_path]=[]
    def undo_crop(self):
        stack=self.crop_undo.get(self.current_path,[])
        if stack:self.crop_redo.setdefault(self.current_path,[]).append(copy.deepcopy(self.regions));self.regions=stack.pop();self.refresh_regions()
    def redo_crop(self):
        stack=self.crop_redo.get(self.current_path,[])
        if stack:self.crop_undo.setdefault(self.current_path,[]).append(copy.deepcopy(self.regions));self.regions=stack.pop();self.refresh_regions()
    def add_region(self,region):self.crop_checkpoint();self.regions.append(region);self.refresh_regions(len(self.regions)-1)
    def remove_region(self):
        i=self.region_list.currentRow()
        if i>=0:self.crop_checkpoint();self.regions.pop(i);self.refresh_regions(max(0,i-1))
    def rotate(self,angle):
        i=self.region_list.currentRow()
        if i>=0:self.crop_checkpoint();self.regions[i].rotation=(self.regions[i].rotation+angle)%360;self.refresh_regions(i)
    def full_image(self):
        if self.current_image:
            w,h=self.current_image.size;self.add_region(CropRegion([(0,0),(w-1,0),(w-1,h-1),(0,h-1)]))
    def detect(self):
        if not self.current_image:return
        image=self.current_image
        def done(regions):self.crop_checkpoint();self.regions=regions;self.refresh_regions();self.notify(f'{len(regions)} regions detected. Draw any missing crops manually.')
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
            if self.on_crops_saved:self.on_crops_saved()
            if isinstance(rows,int):self.refresh_tray();self.side_tabs.setCurrentIndex(1);self.notify(f'{rows} numbered photos saved to your library.');return
            total=sum(p.image.width*p.image.height for p in self.tray.items)+sum(im.width*im.height for _,im in rows)
            if total>self.tray.max_pixels:raise ValueError('The crop tray is full. Remove unused crops first.')
            for name,image in rows:self.tray.add(name,image,path)
            self.refresh_tray();self.notify(f'{len(rows)} crops kept. Choose one for portrait print or two for joint print.')
        self.run(process,done)
    def refresh_tray(self):
        self.tray_label.setText(f'Saved library · {len(self.tray.items)} photos');self.filter_tray(self.search.text())
    def filter_tray(self,text):
        from PySide6.QtGui import QIcon
        self.tray_list.rebuilding=True;self.tray_list.clear();matches=self.tray.query(text,'newest' if self.sort.currentIndex()==0 else 'oldest',self.kind_filter.currentText(),self.deleted.currentIndex()==1)
        for p in matches:
            item=QListWidgetItem(QIcon(pixmap(p.thumbnail((58,70)))),p.display_name);item.setData(Qt.UserRole,p.id);item.setToolTip(p.display_name+' · '+p.kind+(' · Removed (recoverable)' if self.deleted.currentIndex()==1 else ' · Available')+' · Double-click to preview');self.tray_list.addItem(item)
        self.visible_items={p.id:p for p in matches}
        self.tray_list.rebuilding=False;self.tray_list.reapply()
    def selection_summary(self):
        rows=self.tray.by_ids(self.tray_list.selected_ids)
        self.selection_count.setText(f'{len(self.tray_list.selected_ids)} selected: '+', '.join(f'#{p.serial:06d}' for p in rows))
    def rename_photo(self):
        selected=self.tray_list.selectedItems()
        if len(selected)!=1:self.notify('Select one library photo to rename.');return
        id=selected[0].data(Qt.UserRole);item=next((p for p in self.tray.items if p.id==id),self.visible_items[id]);name,ok=QInputDialog.getText(self,'Rename photo','Photo name',text=item.name)
        if ok and name.strip():self.tray.rename(item,name);self.refresh_tray()
    def remove_from_tray(self):self.tray.remove(set(self.tray_list.selected_ids));self.tray_list.clear_selection();self.refresh_tray()
    def restore_selected(self):self.tray.restore_items(set(self.tray_list.selected_ids));self.tray_list.clear_selection();self.refresh_tray()
    def mark_kind(self,kind):self.tray.set_kind(set(self.tray_list.selected_ids),kind);self.refresh_tray()
    def show_preview(self,image,title):
        dialog=QDialog(self);dialog.setWindowTitle(title);layout=QVBoxLayout(dialog);label=QLabel();label.setAlignment(Qt.AlignCenter);label.setPixmap(pixmap(image));layout.addWidget(label);buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.resize(image.width+40,image.height+80);dialog.exec()
    def preview_crop(self):
        index=self.region_list.currentRow()
        if self.current_image is None or index<0:return
        image=self.current_image;region=copy.deepcopy(self.regions[index])
        def preview():
            im=extract_region(image,region);im.thumbnail((800,650));return im
        self.run(preview,lambda im:self.show_preview(im,f'Crop {index+1} · preview before saving'))
    def preview_library(self):
        selected=self.tray_list.selectedItems()
        if len(selected)!=1:return
        item=self.visible_items[selected[0].data(Qt.UserRole)]
        def preview():
            im=item.image;im.thumbnail((850,650));return im
        self.run(preview,lambda im:self.show_preview(im,item.display_name+' · '+item.kind))
    def use_selected(self,mode):
        if self.deleted.currentIndex()==1:self.notify('Restore removed photos before using them in a new job. Existing saved jobs remain available.');return
        ids=self.tray_list.selected_ids;items=self.tray.by_ids(ids);count=1 if mode=='portrait' else 2
        if len(items) not in ((1,) if mode=='portrait' else (1,2)):self.notify('Select one portrait, or one combined/two separate photos for joint print.');return
        self.use(mode,items)

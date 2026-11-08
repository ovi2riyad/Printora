"""Interactive, proportional layer transforms and nondestructive mask brushing."""
import math
import copy
from PySide6.QtCore import Qt,Signal,QRectF,QPointF
from PySide6.QtGui import QColor,QPen,QPainterPath,QTransform
from app.services.selections import TOOLS,combine,selection_mask
from PySide6.QtWidgets import QGraphicsView,QGraphicsItem,QGraphicsPixmapItem,QGraphicsRectItem,QGraphicsEllipseItem
from app.ui.canvas import EditorCanvas,pixmap

class TransformHandle(QGraphicsRectItem):
    def __init__(self,parent,point,owner,rotate=False):
        super().__init__(-4,-4,8,8,parent);self.owner=owner;self.rotate=rotate;self.setPos(point);self.setBrush(QColor('white'));self.setPen(QPen(QColor('#248775'),1));self.setFlag(QGraphicsItem.ItemIgnoresTransformations);self.setZValue(8);self.setCursor(Qt.CrossCursor if rotate else Qt.SizeFDiagCursor)
    def mousePressEvent(self,e):
        self.origin=e.scenePos();item=self.owner;self.center=item.pos();delta=self.origin-self.center;self.distance=max(1,math.hypot(delta.x(),delta.y()));self.angle=math.degrees(math.atan2(delta.y(),delta.x()));self.initial_scale=item.scale();self.initial_rotation=item.rotation();e.accept()
    def mouseMoveEvent(self,e):
        item=self.owner;delta=e.scenePos()-self.center
        if self.rotate:item.setRotation(self.initial_rotation+math.degrees(math.atan2(delta.y(),delta.x()))-self.angle)
        else:item.setScale(max(.01,self.initial_scale*math.hypot(delta.x(),delta.y())/self.distance))
        e.accept()
    def mouseReleaseEvent(self,e):self.owner.commit();e.accept()

class LayerItem(QGraphicsPixmapItem):
    def __init__(self,image,index,layer,canvas,parent):
        super().__init__(pixmap(image),parent);self.index=index;self.layer=layer;self.canvas=canvas;self.setTransformationMode(Qt.SmoothTransformation)
        self.setOffset(-image.width/2,-image.height/2);W,H=canvas.photo_width,canvas.photo_height;self.base=max(W/image.width,H/image.height)
        self.setPos(layer.x*W,layer.y*H);self.setScale(self.base*layer.scale);self.setRotation(-layer.rotation);self.setZValue(index+1);self.setVisible(layer.visible)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        if not layer.locked:self.setFlags(self.flags()|QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable)
        self.outline=QGraphicsRectItem(self.boundingRect());canvas.scene().addItem(self.outline);self.outline.setZValue(1000+index);pen=QPen(QColor('#248775'),1.5);pen.setCosmetic(True);self.outline.setPen(pen);self.outline.setAcceptedMouseButtons(Qt.NoButton);self.outline.hide();self.handles=[]
        r=self.boundingRect()
        for p in (r.topLeft(),r.topRight(),r.bottomLeft(),r.bottomRight()):self.handles.append(TransformHandle(self.outline,p,self))
        self.handles.append(TransformHandle(self.outline,QPointF(0,r.top()-28/self.scale()),self,True));self.sync_overlay()
        for h in self.handles:h.hide()
    def selected_state(self,selected):
        show=selected and self.layer.visible;self.outline.setVisible(show)
        pen=QPen(QColor('#095de5'),3);pen.setCosmetic(True);self.outline.setPen(pen)
        for h in self.handles:h.setVisible(show and not self.layer.locked and self.canvas.tool=='move')
    def sync_overlay(self):
        if hasattr(self,'outline'):self.outline.setPos(self.pos());self.outline.setScale(self.scale());self.outline.setRotation(self.rotation())
    def itemChange(self,change,value):
        if change in (QGraphicsItem.ItemPositionHasChanged,QGraphicsItem.ItemScaleHasChanged,QGraphicsItem.ItemRotationHasChanged):self.sync_overlay()
        return super().itemChange(change,value)
    def mousePressEvent(self,e):
        self.canvas.select_index(self.index);self.canvas.layer_selected.emit(self.index);super().mousePressEvent(e)
    def mouseMoveEvent(self,e):
        super().mouseMoveEvent(e)
        tolerance=4/max(.01,self.canvas.transform().m11());x,y=self.pos().x(),self.pos().y()
        if abs(x-self.canvas.photo_width/2)<tolerance:self.setX(self.canvas.photo_width/2)
        if abs(y-self.canvas.photo_height/2)<tolerance:self.setY(self.canvas.photo_height/2)
    def mouseReleaseEvent(self,e):super().mouseReleaseEvent(e);self.commit()
    def commit(self):
        self.canvas.transformed.emit(self.index,self.x()/self.canvas.photo_width,self.y()/self.canvas.photo_height,self.scale()/self.base,-self.rotation())

class TransformCanvas(EditorCanvas):
    transformed=Signal(int,float,float,float,float)
    layer_selected=Signal(int)
    painted=Signal(int,object)
    tool_changed=Signal(str)
    brush_changed=Signal(int)
    selection_changed=Signal()
    selection_error=Signal(str)
    def __init__(self):
        super().__init__();self.photo_width=1;self.photo_height=1;self.layers=[];self.active=0;self.tool='move';self.brush_size=24;self.stroke=None;self.hover=None;self.panning=False;self.ready=False;self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus)
        self.selection=None;self.selection_mode='new';self.gesture=None;self.selection_path=QPainterPath();self.selection_owner=None
        self.setMinimumSize(260,240)
        self.preview_obstruction=0;self.preview_fitted=True
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    def fit_preview(self):
        """Fit the actual photo, using the height and space beside floating controls."""
        self.preview_fitted=True
        bounds=getattr(self,'photo_rect',self.sceneRect())
        if bounds.width()<=0 or bounds.height()<=0:return
        available=max(40,self.viewport().width()-self.preview_obstruction)
        scale=min(max(20,available-20)/bounds.width(),max(20,self.viewport().height()-20)/bounds.height())
        self.setTransform(QTransform.fromScale(scale,scale))
        center=bounds.center();center.setX(center.x()+self.preview_obstruction/(2*scale));self.centerOn(center)
    def set_preview_obstruction(self,width):
        if width!=self.preview_obstruction:
            self.preview_obstruction=width
            if self.preview_fitted:self.fit_preview()
    def resizeEvent(self,event):
        # The base canvas fits its entire scene, including off-photo editing space.
        QGraphicsView.resizeEvent(self,event)
        if self.preview_fitted:self.fit_preview()
    def display(self,image):
        self.layers=[];self.ready=False;self.selection=None;self.gesture=None;self.selection_owner=None;self.photo_rect=QRectF(0,0,image.width,image.height);super().display(image)
    def set_layers(self,photo,images,index=0):
        new_document=not self.ready or photo.id!=getattr(self,'document_id',None);self.document_id=photo.id
        self.composition=photo.composition
        W=round(photo.width/25.4*140);H=round(photo.height/25.4*140);changed_size=(W,H)!=(self.photo_width,self.photo_height);self.photo_width=W;self.photo_height=H
        self.scene().clear();self.layers=[]
        frame=self.scene().addRect(0,0,W,H,QPen(QColor('#9caaba')),QColor(photo.background));frame.setFlag(QGraphicsItem.ItemClipsChildrenToShape)
        self.photo_rect=QRectF(0,0,W,H);self.setSceneRect(-2*W,-2*H,5*W,5*H)
        for i,(layer,image) in enumerate(zip(photo.layers,images)):self.layers.append(LayerItem(image,i,layer,self,frame))
        self.active=index;self.ready=True;self.select_index(index)
        if photo.border and photo.border_mm:
            b=photo.border_mm/25.4*140;pen=QPen(QColor(photo.border_color),b);border=self.scene().addRect(b/2,b/2,W-b,H-b,pen);border.setZValue(100);border.setAcceptedMouseButtons(Qt.NoButton)
        if changed_size or new_document or self.transform().isIdentity():self.fit_preview()
    def select_index(self,index):
        self.active=index
        owner=(getattr(self,'document_id',None),index,self.layers[index].layer.source,self.layers[index].layer.label) if 0<=index<len(self.layers) else None
        if owner!=self.selection_owner:self.selection_owner=owner;self.selection=None;self.gesture=None
        self.update_selection_path()
        for i,item in enumerate(self.layers):item.selected_state(i==index)
    def editable_item(self):
        if self.ready and 0<=self.active<len(self.layers):
            item=self.layers[self.active]
            if item.layer.visible and not item.layer.locked:return item
        return None
    def source_point(self,event):
        item=self.editable_item()
        if item is None:return None
        p=item.mapFromScene(self.mapToScene(event.position().toPoint()))
        x,y=p.x()/item.pixmap().width()+.5,p.y()/item.pixmap().height()+.5
        return [1-x if item.layer.flip_h else x,1-y if item.layer.flip_v else y]
    def set_selection(self,expression):
        previous=self.selection;self.selection=copy.deepcopy(expression)
        try:self.update_selection_path()
        except (ValueError,KeyError,TypeError) as error:self.selection=previous;self.selection_error.emit(str(error));self.update_selection_path();return
        self.selection_changed.emit();self.viewport().update()
    def update_selection_path(self):
        self.selection_path=QPainterPath()
        if not self.selection or not 0<=self.active<len(self.layers):return
        import cv2
        import numpy as np
        item=self.layers[self.active];w,h=item.pixmap().width(),item.pixmap().height()
        # Bound contour work independently of camera resolution.
        ratio=min(1,900/max(w,h));sw,sh=max(1,round(w*ratio)),max(1,round(h*ratio))
        mask=np.array(selection_mask(self.selection,(sw,sh)))
        if item.layer.flip_h:mask=np.fliplr(mask)
        if item.layer.flip_v:mask=np.flipud(mask)
        contours,_=cv2.findContours(mask.copy(),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            points=contour[:,0,:]
            if len(points)<2:continue
            self.selection_path.moveTo(float(points[0,0])*w/sw-w/2,float(points[0,1])*h/sh-h/2)
            for x,y in points[1:]:self.selection_path.lineTo(float(x)*w/sw-w/2,float(y)*h/sh-h/2)
            self.selection_path.closeSubpath()
    def modify_selection(self,operation,radius=0):
        if operation=='all':self.set_selection({'kind':'all'})
        elif operation=='deselect':self.set_selection(None)
        elif self.selection:self.set_selection({'kind':operation,'selection':self.selection,'radius':radius})
    def edit_selection(self,restore=False):
        if self.selection and self.editable_item():self.painted.emit(self.active,{'kind':'selection','mode':'restore_selection' if restore else 'erase','selection':copy.deepcopy(self.selection)})
    def finish_selection(self):
        if self.gesture:
            shape=self.gesture;mode=shape.pop('operation',self.selection_mode);shape.pop('constrain',None);self.gesture=None
            if shape['kind'] not in ('polygon','lasso') or len(shape['points'])>=3:self.set_selection(combine(self.selection,shape,mode))
    def gesture_point(self,event):
        point=self.source_point(event)
        if point and self.gesture and self.tool in ('rectangle','ellipse') and (self.gesture.get('constrain') or event.modifiers()&Qt.ShiftModifier):
            # Constraint is in source pixels, including on rotated/flipped layers.
            start=self.gesture['points'][0];item=self.editable_item();w,h=item.pixmap().width(),item.pixmap().height()
            dx,dy=(point[0]-start[0])*w,(point[1]-start[1])*h;side=max(abs(dx),abs(dy))
            point=[start[0]+math.copysign(side,dx)/w,start[1]+math.copysign(side,dy)/h]
        return point
    def set_tool(self,tool):
        if tool!=self.tool:self.gesture=None
        self.shape_constraint=False
        self.tool=tool;self.select_index(self.active);self.setCursor(Qt.CrossCursor if tool!='move' else Qt.ArrowCursor);self.viewport().update();self.tool_changed.emit(tool)
    def mousePressEvent(self,e):
        if self.panning:QGraphicsView.mousePressEvent(self,e);return
        if self.ready and self.tool in TOOLS:
            if e.button()!=Qt.LeftButton:return
            point=self.source_point(e)
            if point is None:return
            if self.tool=='polygon' and self.gesture:self.gesture['points'].append(point);self.viewport().update();return
            modifiers=e.modifiers();mode='subtract' if modifiers&Qt.AltModifier else 'add' if modifiers&Qt.ControlModifier else self.selection_mode
            item=self.editable_item();self.gesture={'kind':self.tool,'points':[point],'operation':mode,'constrain':bool(modifiers&Qt.ShiftModifier) or getattr(self,'shape_constraint',False),'radius':self.brush_size/2/max(.001,item.scale())/item.pixmap().width()};self.viewport().update();return
        if self.ready and self.tool in ('erase','restore') and 0<=self.active<len(self.layers):
            item=self.layers[self.active]
            if item.layer.locked or not item.layer.visible:return
            self.stroke={'mode':self.tool,'points':[],'radius':self.brush_size/2/max(.001,item.scale())/item.pixmap().width(),'hardness':getattr(self,'brush_hardness',.75),'opacity':getattr(self,'brush_opacity',1.),'feather':getattr(self,'brush_feather',0)/item.pixmap().width()};self.append_stroke(e);return

        QGraphicsView.mousePressEvent(self,e)
    def append_stroke(self,e):
        item=self.layers[self.active];point=item.mapFromScene(self.mapToScene(e.position().toPoint()));x=point.x()/item.pixmap().width()+.5;y=point.y()/item.pixmap().height()+.5
        if item.layer.flip_h:x=1-x
        if item.layer.flip_v:y=1-y
        self.stroke['points'].append([x,y]);self.hover=self.mapToScene(e.position().toPoint());self.viewport().update()
        if self.selection:self.stroke['clip_selection']=copy.deepcopy(self.selection)
    def mouseMoveEvent(self,e):
        self.hover=self.mapToScene(e.position().toPoint())
        if self.gesture:
            p=self.gesture_point(e)
            if p and self.tool!='polygon':
                if self.tool in ('rectangle','ellipse'):self.gesture['points']=self.gesture['points'][:1]+[p]
                elif len(self.gesture['points'])<8192:self.gesture['points'].append(p)
            self.viewport().update();return
        if self.stroke is not None:self.append_stroke(e);return
        QGraphicsView.mouseMoveEvent(self,e);self.viewport().update()
    def mouseReleaseEvent(self,e):
        if self.gesture and self.tool!='polygon':
            p=self.gesture_point(e)
            if p:
                if self.tool in ('rectangle','ellipse'):self.gesture['points']=self.gesture['points'][:1]+[p]
                elif len(self.gesture['points'])<8192:self.gesture['points'].append(p)
            self.finish_selection();return
        if self.stroke is not None:
            self.append_stroke(e);stroke=self.stroke;self.stroke=None;self.painted.emit(self.active,stroke);self.viewport().update();return
        QGraphicsView.mouseReleaseEvent(self,e)
    def mouseDoubleClickEvent(self,e):
        if self.tool=='polygon' and self.gesture:self.finish_selection();return
        super().mouseDoubleClickEvent(e)
    def wheelEvent(self,e):
        if e.modifiers()&Qt.ControlModifier:
            self.preview_fitted=False
            factor=1.15 if e.angleDelta().y()>0 else 1/1.15;self.scale(factor,factor)
        else:self.zoomed.emit(1.05 if e.angleDelta().y()>0 else 1/1.05)
    def keyPressEvent(self,e):
        if e.modifiers()&Qt.ControlModifier and e.key() in (Qt.Key_A,Qt.Key_D,Qt.Key_I):
            self.modify_selection({Qt.Key_A:'all',Qt.Key_D:'deselect',Qt.Key_I:'invert'}[e.key()]);e.accept();return
        if e.key() in (Qt.Key_Delete,Qt.Key_Backspace):self.edit_selection();e.accept();return
        if e.key() in (Qt.Key_Enter,Qt.Key_Return) and self.gesture:self.finish_selection();e.accept();return
        if e.key() in (Qt.Key_M,Qt.Key_L,Qt.Key_B):
            shift=bool(e.modifiers()&Qt.ShiftModifier);tool=('ellipse' if shift else 'rectangle') if e.key()==Qt.Key_M else ('polygon' if shift else 'lasso') if e.key()==Qt.Key_L else 'selection_brush';self.set_tool(tool);e.accept();return
        if e.key() in (Qt.Key_BracketLeft,Qt.Key_BracketRight):self.brush_size=max(4,min(150,self.brush_size+(-4 if e.key()==Qt.Key_BracketLeft else 4)));self.brush_changed.emit(self.brush_size);e.accept();return
        if e.key()==Qt.Key_Escape:self.gesture=None;self.modify_selection('deselect');self.set_tool('move');e.accept();return
        if e.key()==Qt.Key_Space and not e.isAutoRepeat():self.panning=True;self.setInteractive(False);self.setDragMode(QGraphicsView.ScrollHandDrag);e.accept();return
        deltas={Qt.Key_Left:(-1,0),Qt.Key_Right:(1,0),Qt.Key_Up:(0,-1),Qt.Key_Down:(0,1)}
        if e.key() in deltas:
            dx,dy=deltas[e.key()];step=10 if e.modifiers()&Qt.ShiftModifier else 1;self.moved.emit(dx*step/self.photo_width,dy*step/self.photo_height);e.accept();return
        if e.key() in (Qt.Key_V,Qt.Key_E,Qt.Key_R):self.set_tool({Qt.Key_V:'move',Qt.Key_E:'erase',Qt.Key_R:'restore'}[e.key()]);e.accept();return
        super().keyPressEvent(e)
    def keyReleaseEvent(self,e):
        if e.key()==Qt.Key_Space:self.panning=False;self.setInteractive(True);self.setDragMode(QGraphicsView.NoDrag);e.accept();return
        super().keyReleaseEvent(e)
    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        item=self.layers[self.active] if self.ready and 0<=self.active<len(self.layers) else None
        if item and item.layer.visible and (self.selection or self.gesture or self.stroke):
            painter.save();painter.setWorldTransform(item.sceneTransform(),True);painter.setBrush(Qt.NoBrush)
            for color,style in [('black',Qt.SolidLine),('white',Qt.DashLine)]:
                pen=QPen(QColor(color),1,style);pen.setCosmetic(True);painter.setPen(pen);painter.drawPath(self.selection_path)
            gesture=self.gesture or self.stroke
            if gesture and gesture.get('points'):
                w,h=item.pixmap().width(),item.pixmap().height();points=[]
                for x,y in gesture['points']:
                    points.append(QPointF((1-x if item.layer.flip_h else x)*w-w/2,(1-y if item.layer.flip_v else y)*h-h/2))
                path=QPainterPath();kind=gesture.get('kind')
                if kind in ('rectangle','ellipse') and len(points)>1:
                    bounds=QRectF(points[0],points[-1]).normalized();path.addRect(bounds) if kind=='rectangle' else path.addEllipse(bounds)
                else:
                    path.moveTo(points[0])
                    for p in points[1:]:path.lineTo(p)
                pen=QPen(QColor('#38bdf8'),2,Qt.DashLine);pen.setCosmetic(True);painter.setPen(pen);painter.drawPath(path)
            painter.restore()
        if self.ready and getattr(self,'safe_area_visible',True):
            W,H=self.photo_width,self.photo_height;settings=getattr(self,'composition',{})
            # Canvas units are 140 DPI; composition margins are physical mm.
            top,bottom,left,right=[settings.get(k,2)/25.4*140 for k in ('top','bottom','left','right')]
            pen=QPen(QColor('#095de5'),1,Qt.DashLine);pen.setCosmetic(True);painter.setPen(pen);painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(left,top,max(0,W-left-right),max(0,H-top-bottom)))
        if self.tool in ('erase','restore','selection_brush') and self.hover is not None:
            pen=QPen(QColor('#e86650') if self.tool=='erase' else QColor('#238d64'),1.2);pen.setCosmetic(True);painter.setPen(pen);painter.drawEllipse(self.hover,self.brush_size/2,self.brush_size/2)

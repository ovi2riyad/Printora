"""Interactive, proportional layer transforms and nondestructive mask brushing."""
import math
from PySide6.QtCore import Qt,Signal,QRectF,QPointF
from PySide6.QtGui import QColor,QPen,QPainterPath
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
        show=selected and self.layer.visible and not self.layer.locked and self.canvas.tool=='move';self.outline.setVisible(show)
        for h in self.handles:h.setVisible(show)
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
    def __init__(self):
        super().__init__();self.photo_width=1;self.photo_height=1;self.layers=[];self.active=0;self.tool='move';self.brush_size=24;self.stroke=None;self.hover=None;self.panning=False;self.ready=False;self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus)
    def display(self,image):
        self.layers=[];self.ready=False;self.photo_rect=QRectF(0,0,image.width,image.height);super().display(image)
    def set_layers(self,photo,images,index=0):
        W=round(photo.width/25.4*140);H=round(photo.height/25.4*140);changed_size=(W,H)!=(self.photo_width,self.photo_height);self.photo_width=W;self.photo_height=H
        self.scene().clear();self.layers=[]
        frame=self.scene().addRect(0,0,W,H,QPen(QColor('#9caaba')),QColor(photo.background));frame.setFlag(QGraphicsItem.ItemClipsChildrenToShape)
        self.photo_rect=QRectF(0,0,W,H);self.setSceneRect(-36,-36,W+72,H+72)
        for i,(layer,image) in enumerate(zip(photo.layers,images)):self.layers.append(LayerItem(image,i,layer,self,frame))
        self.active=index;self.ready=True;self.select_index(index)
        if photo.border and photo.border_mm:
            b=photo.border_mm/25.4*140;pen=QPen(QColor(photo.border_color),b);border=self.scene().addRect(b/2,b/2,W-b,H-b,pen);border.setZValue(100);border.setAcceptedMouseButtons(Qt.NoButton)
        if changed_size or self.transform().isIdentity():self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
    def select_index(self,index):
        self.active=index
        for i,item in enumerate(self.layers):item.selected_state(i==index)
    def set_tool(self,tool):
        self.tool=tool;self.select_index(self.active);self.setCursor(Qt.CrossCursor if tool!='move' else Qt.ArrowCursor);self.viewport().update();self.tool_changed.emit(tool)
    def mousePressEvent(self,e):
        if self.panning:QGraphicsView.mousePressEvent(self,e);return
        if self.ready and self.tool in ('erase','restore') and 0<=self.active<len(self.layers):
            item=self.layers[self.active]
            if item.layer.locked:return
            self.stroke={'mode':self.tool,'points':[],'radius':self.brush_size/2/max(.001,item.scale())/item.pixmap().width()};self.append_stroke(e);return
        QGraphicsView.mousePressEvent(self,e)
    def append_stroke(self,e):
        item=self.layers[self.active];point=item.mapFromScene(self.mapToScene(e.position().toPoint()));x=point.x()/item.pixmap().width()+.5;y=point.y()/item.pixmap().height()+.5
        if item.layer.flip_h:x=1-x
        if item.layer.flip_v:y=1-y
        self.stroke['points'].append([x,y]);self.hover=self.mapToScene(e.position().toPoint());self.viewport().update()
    def mouseMoveEvent(self,e):
        self.hover=self.mapToScene(e.position().toPoint())
        if self.stroke is not None:self.append_stroke(e);return
        QGraphicsView.mouseMoveEvent(self,e);self.viewport().update()
    def mouseReleaseEvent(self,e):
        if self.stroke is not None:
            self.append_stroke(e);stroke=self.stroke;self.stroke=None;self.painted.emit(self.active,stroke);self.viewport().update();return
        QGraphicsView.mouseReleaseEvent(self,e)
    def wheelEvent(self,e):
        if e.modifiers()&Qt.ControlModifier:
            factor=1.15 if e.angleDelta().y()>0 else 1/1.15;self.scale(factor,factor)
        else:self.zoomed.emit(1.05 if e.angleDelta().y()>0 else 1/1.05)
    def keyPressEvent(self,e):
        if e.key() in (Qt.Key_BracketLeft,Qt.Key_BracketRight):self.brush_size=max(4,min(150,self.brush_size+(-4 if e.key()==Qt.Key_BracketLeft else 4)));self.brush_changed.emit(self.brush_size);e.accept();return
        if e.key()==Qt.Key_Escape:self.set_tool('move');e.accept();return
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
        if self.tool!='move' and self.hover is not None:
            pen=QPen(QColor('#e86650') if self.tool=='erase' else QColor('#238d64'),1.2);pen.setCosmetic(True);painter.setPen(pen);painter.drawEllipse(self.hover,self.brush_size/2,self.brush_size/2)

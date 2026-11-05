from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt,Signal,QRectF
from PySide6.QtGui import QPixmap,QPen,QColor,QPainter,QPainterPath,QTransform
from PySide6.QtWidgets import QGraphicsView,QGraphicsScene,QGraphicsPixmapItem,QGraphicsItem,QGraphicsRectItem
from app.services.layout import page_size

def pixmap(im): return QPixmap.fromImage(ImageQt(im.convert('RGBA')))

class EditorCanvas(QGraphicsView):
    moved=Signal(float,float)
    zoomed=Signal(float)
    def __init__(self):
        super().__init__();self.setScene(QGraphicsScene(self));self.setRenderHint(QPainter.Antialiasing);self.setMinimumSize(350,400);self.start=None;self.guide_count=0
    def set_guides(self,count):
        self.guide_count=count;self.viewport().update()
    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        bounds=getattr(self,'photo_rect',self.sceneRect());w,h=bounds.width(),bounds.height()
        if not self.guide_count or w<=1:return
        painter.save();pen=QPen(QColor('#38d9ed'));pen.setWidthF(1.7);pen.setCosmetic(True);pen.setStyle(Qt.DashLine);painter.setPen(pen)
        centers=[.5] if self.guide_count==1 else [.27,.73]
        for cx in centers:
            half=.18 if self.guide_count==1 else .13
            painter.drawEllipse(QRectF((cx-half)*w,.15*h,half*2*w,.42*h))
            painter.drawLine((cx-half)*w,.34*h,(cx+half)*w,.34*h)
            path=QPainterPath();path.moveTo((cx-half*1.9)*w,.93*h);path.cubicTo((cx-half*1.8)*w,.65*h,(cx-half*.8)*w,.67*h,(cx-half*.5)*w,.60*h)
            path.moveTo((cx+half*.5)*w,.60*h);path.cubicTo((cx+half*.8)*w,.67*h,(cx+half*1.8)*w,.65*h,(cx+half*1.9)*w,.93*h);painter.drawPath(path)
            painter.drawLine(cx*w,.08*h,cx*w,.94*h)
        painter.restore()
    def display(self,im):
        self.scene().clear();self.scene().addPixmap(pixmap(im));self.setSceneRect(0,0,im.width,im.height);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
    def resizeEvent(self,e):
        super().resizeEvent(e);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
    def mousePressEvent(self,e):
        self.start=self.mapToScene(e.position().toPoint());super().mousePressEvent(e)
    def mouseReleaseEvent(self,e):
        if self.start is not None and self.sceneRect().width():
            end=self.mapToScene(e.position().toPoint());self.moved.emit((end.x()-self.start.x())/self.sceneRect().width(),(end.y()-self.start.y())/self.sceneRect().height());self.start=None
        super().mouseReleaseEvent(e)
    def wheelEvent(self,e): self.zoomed.emit(1.08 if e.angleDelta().y()>0 else 1/1.08)

class PrintItem(QGraphicsPixmapItem):
    def __init__(self,im,placement,pw,ph,on_move,margin=0,photo=None):
        super().__init__(pixmap(im));self.r=placement;self.pw=pw;self.ph=ph;self.on_move=on_move;self.margin=margin
        self.setTransformationMode(Qt.SmoothTransformation);self.setTransform(QTransform.fromScale(placement.width*3/self.pixmap().width(),placement.height*3/self.pixmap().height()));self.setPos(placement.x*3,placement.y*3)
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable)
        if photo is not None and photo.border and photo.border_mm:
            # Cancel the pixmap transform for a border measured in page units.
            # This matches the PDF stroke exactly, even at fractional raster pixels.
            width,height=placement.width*3,placement.height*3;b=photo.border_mm*3
            self.border_item=QGraphicsRectItem(b/2,b/2,width-b,height-b,self)
            self.border_item.setTransform(QTransform.fromScale(self.pixmap().width()/width,self.pixmap().height()/height))
            self.border_item.setPen(QPen(QColor(photo.border_color),b));self.border_item.setAcceptedMouseButtons(Qt.NoButton)
    def mouseReleaseEvent(self,e):
        super().mouseReleaseEvent(e)
        self.r.x=max(self.margin,min(self.pw-self.margin-self.r.width,round(self.x()/3*2)/2))
        self.r.y=max(self.margin,min(self.ph-self.margin-self.r.height,round(self.y()/3*2)/2))
        self.setPos(self.r.x*3,self.r.y*3);self.on_move()

class PrintCanvas(QGraphicsView):
    changed=Signal()
    def __init__(self):
        super().__init__();self.setScene(QGraphicsScene(self));self.setRenderHint(QPainter.Antialiasing);self.setMinimumSize(400,450)
    def display(self,job,page,images,vector_borders=False):
        self.scene().clear();pw,ph=page_size(job.print_settings)
        self.scene().addRect(0,0,pw*3,ph*3,QPen(QColor('#cccccc')),QColor('white'))
        m=job.print_settings['margin']*3
        pen=QPen(QColor('#b8c5d1'));pen.setStyle(Qt.DashLine)
        self.scene().addRect(m,m,pw*3-2*m,ph*3-2*m,pen)
        photos={p.id:p for p in job.photos}
        for r in job.placements:
            if r.page!=page or r.photo_id not in images:continue
            self.scene().addItem(PrintItem(images[r.photo_id],r,pw,ph,self.changed.emit,job.print_settings.get('margin',0) if job.print_settings.get('enforce_margins') else 0,photos[r.photo_id] if vector_borders else None))
            if job.print_settings.get('guides'):
                guide=QPen(QColor('#808080'));guide.setWidthF(.3)
                for x,y,sx,sy in [(r.x,r.y,-1,-1),(r.x+r.width,r.y,1,-1),(r.x,r.y+r.height,-1,1),(r.x+r.width,r.y+r.height,1,1)]:
                    self.scene().addLine((x+sx*.5)*3,y*3,(x+sx*2)*3,y*3,guide)
                    self.scene().addLine(x*3,(y+sy*.5)*3,x*3,(y+sy*2)*3,guide)
        self.setSceneRect(-8,-8,pw*3+16,ph*3+16);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
    def resizeEvent(self,e):
        super().resizeEvent(e);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)

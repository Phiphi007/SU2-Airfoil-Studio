#include "fieldview.h"
#include <QDataStream>
#include <QFile>
#include <QLinearGradient>
#include <QMouseEvent>
#include <QPainter>
#include <QWheelEvent>
#include <cmath>

FieldView::FieldView(QWidget *parent) : QWidget(parent) {
    setMinimumSize(480,300);
    setMouseTracking(true);
}

bool FieldView::loadData(const QString &path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return false;
    QDataStream stream(&file);
    stream.setByteOrder(QDataStream::LittleEndian);
    stream.setFloatingPointPrecision(QDataStream::SinglePrecision);
    char magic[8];
    if (stream.readRawData(magic,8)!=8 || QByteArray(magic,8)!=QByteArray("SAFV1\0\0\0",8)) return false;
    quint32 nodeCount=0,cellCount=0,boundaryCount=0,flags=0;
    stream >> nodeCount >> cellCount >> boundaryCount >> flags;
    if (!nodeCount || nodeCount>10000000 || cellCount>20000000 || boundaryCount>1000000 || flags>1) return false;
    float xmin,xmax,ymin,ymax,vmin,vmax;
    stream >> xmin >> xmax >> ymin >> ymax >> vmin >> vmax;
    if (!(xmin<xmax && ymin<ymax && std::isfinite(xmin) && std::isfinite(xmax)
          && std::isfinite(ymin) && std::isfinite(ymax))) return false;
    QVector<QPointF> nodes;nodes.reserve(nodeCount);
    for (quint32 i=0;i<nodeCount;++i) {float x,y;stream >> x >> y;nodes.append(QPointF(x,y));}
    QVector<quint32> indices;indices.reserve(cellCount*4);
    for (quint32 i=0;i<cellCount*4;++i) {quint32 value;stream >> value;if(value>=nodeCount)return false;indices.append(value);}
    QPolygonF wall;wall.reserve(boundaryCount);
    for (quint32 i=0;i<boundaryCount;++i) {float x,y;stream >> x >> y;wall << QPointF(x,y);}
    QVector<float> values;
    if (flags) {values.reserve(nodeCount);for (quint32 i=0;i<nodeCount;++i) {float value;stream >> value;values.append(value);}}
    if (stream.status()!=QDataStream::Ok) return false;
    QVector<Cell> cells;cells.reserve(cellCount);
    for (quint32 i=0;i<cellCount;++i) {
        Cell cell;
        for (quint32 j=0;j<4;++j) {
            const auto index=indices[i*4+j];cell.polygon << nodes[index];
            if(flags) cell.value+=values[index]*0.25f;
        }
        cells.append(cell);
    }
    cells_=std::move(cells);boundary_=wall;
    bounds_=QRectF(QPointF(xmin,ymin),QPointF(xmax,ymax));
    minimum_=vmin;maximum_=vmax;hasField_=flags;
    resetView();return true;
}

void FieldView::resetView() {zoom_=1;pan_=QPointF();update();}

QColor FieldView::fieldColor(double value) const {
    static const QColor stops[] = {QColor("#440154"),QColor("#3b528b"),QColor("#21918c"),QColor("#5ec962"),QColor("#fde725")};
    const double t=qBound(0.0,(value-minimum_)/qMax(1e-12f,maximum_-minimum_),1.0)*4.0;
    const int index=qMin(3,int(t));const double blend=t-index;
    return QColor::fromRgbF((1-blend)*stops[index].redF()+blend*stops[index+1].redF(),
                            (1-blend)*stops[index].greenF()+blend*stops[index+1].greenF(),
                            (1-blend)*stops[index].blueF()+blend*stops[index+1].blueF());
}

void FieldView::paintEvent(QPaintEvent *) {
    QPainter painter(this);painter.fillRect(rect(),palette().color(QPalette::Base));
    if (cells_.isEmpty()) return;
    painter.setRenderHint(QPainter::Antialiasing,!hasField_);
    const double usableWidth=width()-(hasField_?125:50);
    const double scale=qMin(usableWidth/bounds_.width(),(height()-50.0)/bounds_.height())*zoom_;
    const QPointF center=bounds_.center();
    painter.save();
    painter.translate((width()-(hasField_?75:0))/2.0+pan_.x(),height()/2.0+pan_.y());
    painter.scale(scale,-scale);painter.translate(-center.x(),-center.y());
    painter.setClipRect(bounds_);
    if (hasField_) painter.setPen(Qt::NoPen);
    else painter.setPen(QPen(QColor("#7895a4"),0));
    for (const Cell &cell:cells_) {
        if (!bounds_.intersects(cell.polygon.boundingRect())) continue;
        if (hasField_) painter.setBrush(fieldColor(cell.value));
        painter.drawPolygon(cell.polygon);
    }
    if (!boundary_.isEmpty()) {
        painter.setPen(QPen(QColor("#17364a"),0));painter.setBrush(Qt::white);
        painter.drawPolygon(boundary_);
    }
    painter.restore();
    if (hasField_) {
        const QRect bar(width()-63,35,18,height()-95);
        QLinearGradient gradient(bar.topLeft(),bar.bottomLeft());
        for (int i=0;i<=4;++i) gradient.setColorAt(i/4.0,fieldColor(maximum_-(maximum_-minimum_)*i/4.0));
        painter.fillRect(bar,gradient);painter.setPen(palette().color(QPalette::Text));
        painter.drawRect(bar);
        painter.drawText(width()-91,25,QStringLiteral("Mach"));
        painter.drawText(bar.right()+5,bar.top()+8,QString::number(maximum_,'f',3));
        painter.drawText(bar.right()+5,bar.bottom(),QString::number(minimum_,'f',3));
    }
}

void FieldView::wheelEvent(QWheelEvent *event) {
    const double factor=std::pow(1.0015,event->angleDelta().y());
    const double next=qBound(0.05,zoom_*factor,80.0);
    const double actual=next/zoom_;
    const QPointF center((width()-(hasField_?75:0))/2.0,height()/2.0);
    pan_+=(1.0-actual)*(event->position()-center-pan_);
    zoom_=next;update();event->accept();
}
void FieldView::mousePressEvent(QMouseEvent *event) {
    if(event->button()==Qt::LeftButton || event->button()==Qt::MiddleButton) {
        dragging_=true;lastMouse_=event->position();setCursor(Qt::ClosedHandCursor);event->accept();
    }
}
void FieldView::mouseMoveEvent(QMouseEvent *event) {
    if(dragging_) {pan_+=event->position()-lastMouse_;lastMouse_=event->position();update();event->accept();}
}
void FieldView::mouseReleaseEvent(QMouseEvent *event) {
    if(dragging_ && (event->button()==Qt::LeftButton || event->button()==Qt::MiddleButton)) {
        dragging_=false;unsetCursor();event->accept();
    }
}

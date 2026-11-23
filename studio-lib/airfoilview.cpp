#include "airfoilview.h"
#include <QFile>
#include <QPainter>
#include <QRegularExpression>
#include <QTextStream>
#include <QPalette>
#include <QEvent>
#include <QWheelEvent>
#include <QMouseEvent>
#include <cmath>
AirfoilView::AirfoilView(QWidget *parent) : QWidget(parent) { setMinimumSize(480, 300); reset(); }
void AirfoilView::reset() {
    QString error;loadNaca4(QStringLiteral("0012"),&error);
}
bool AirfoilView::loadNaca4(const QString &designation, QString *error) {
    if (!QRegularExpression(QStringLiteral("^[0-9]{4}$")).match(designation).hasMatch()) {
        if (error) *error=tr("Enter a four-digit NACA designation.");
        return false;
    }
    const double m=designation.mid(0,1).toInt()/100.0;
    const double camberPosition=designation.mid(1,1).toInt()/10.0;
    const double thickness=designation.mid(2,2).toInt()/100.0;
    if ((m>0 && (camberPosition<=0 || camberPosition>=1)) || thickness<=0) {
        if (error) *error=tr("Invalid NACA camber or thickness.");
        return false;
    }
    zoom_=1.0;pan_=QPointF();
    points_.clear();
    auto coordinates=[&](double x, bool upper) {
        const double yt=5*thickness*(0.2969*std::sqrt(x)-0.1260*x-0.3516*x*x+0.2843*x*x*x-0.1036*x*x*x*x);
        double yc=0,dyc=0;
        if (m>0) {
            if (x<camberPosition) {
                yc=m/(camberPosition*camberPosition)*(2*camberPosition*x-x*x);
                dyc=2*m/(camberPosition*camberPosition)*(camberPosition-x);
            } else {
                yc=m/((1-camberPosition)*(1-camberPosition))*(1-2*camberPosition+2*camberPosition*x-x*x);
                dyc=2*m/((1-camberPosition)*(1-camberPosition))*(camberPosition-x);
            }
        }
        const double theta=std::atan(dyc),side=upper?1.0:-1.0;
        return QPointF(x-side*yt*std::sin(theta),yc+side*yt*std::cos(theta));
    };
    for (int i=0;i<=100;++i) {
        const double x=(1+std::cos(3.14159265358979323846*i/100.0))/2;
        points_.append(coordinates(x,true));
    }
    for (int i=1;i<=100;++i) {
        const double x=(1-std::cos(3.14159265358979323846*i/100.0))/2;
        points_.append(coordinates(x,false));
    }
    update();
    return true;
}
bool AirfoilView::loadDat(const QString &path, QString *error) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) { *error = file.errorString(); return false; }
    QVector<QPointF> parsed;
    QTextStream stream(&file);
    while (!stream.atEnd()) {
        const QStringList fields = stream.readLine().trimmed().split(QRegularExpression("\\s+"), Qt::SkipEmptyParts);
        if (fields.size() < 2) continue;
        bool xOk=false, yOk=false;
        const double x=fields[0].toDouble(&xOk), y=fields[1].toDouble(&yOk);
        if (xOk && yOk && std::isfinite(x) && std::isfinite(y)) parsed.append({x,y});
    }
    if (parsed.size() < 3) { *error = tr("The DAT file has fewer than three coordinate pairs."); return false; }
    points_ = parsed;zoom_=1.0;pan_=QPointF();update(); return true;
}
bool AirfoilView::saveDat(const QString &path, QString *error) const {
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) { if (error) *error=file.errorString(); return false; }
    QTextStream stream(&file);
    stream << "Airfoil exported by SU2 Airfoil Studio\n";
    for (const auto &point : points_) stream << QString::number(point.x(),'g',17) << ' ' << QString::number(point.y(),'g',17) << '\n';
    return stream.status()==QTextStream::Ok;
}
void AirfoilView::changeEvent(QEvent *event) { QWidget::changeEvent(event); if(event->type()==QEvent::PaletteChange) update(); }
void AirfoilView::wheelEvent(QWheelEvent *event) {
    const double factor=std::pow(1.0015,event->angleDelta().y());
    const double next=qBound(0.1,zoom_*factor,30.0);
    const double actual=next/zoom_;
    const QPointF center=rect().center();
    const QPointF offset=event->position()-center-pan_;
    pan_+=(1.0-actual)*offset;
    zoom_=next;update();event->accept();
}
void AirfoilView::mousePressEvent(QMouseEvent *event) {
    if(event->button()==Qt::LeftButton || event->button()==Qt::MiddleButton) {
        dragging_=true;lastMouse_=event->position();setCursor(Qt::ClosedHandCursor);event->accept();
    }
}
void AirfoilView::mouseMoveEvent(QMouseEvent *event) {
    if(dragging_) {pan_+=event->position()-lastMouse_;lastMouse_=event->position();update();event->accept();}
}
void AirfoilView::mouseReleaseEvent(QMouseEvent *event) {
    if(dragging_ && (event->button()==Qt::LeftButton || event->button()==Qt::MiddleButton)) {
        dragging_=false;unsetCursor();event->accept();
    }
}
void AirfoilView::paintEvent(QPaintEvent *) {
    const bool dark=palette().color(QPalette::Window).lightness()<128;
    QPainter p(this); p.fillRect(rect(), palette().color(QPalette::Base)); p.setRenderHint(QPainter::Antialiasing);
    p.save();
    const QPointF center=rect().center();
    p.translate(center+pan_);p.scale(zoom_,zoom_);p.translate(-center);
    const QRectF area=rect().adjusted(44,40,-36,-44);
    p.setPen(QPen(QColor(dark?"#273747":"#d9e1e8"),1));
    for (int i=0;i<=10;++i) { double x=area.left()+area.width()*i/10; p.drawLine(QPointF(x,area.top()),QPointF(x,area.bottom())); }
    for (int i=0;i<=4;++i) { double y=area.top()+area.height()*i/4; p.drawLine(QPointF(area.left(),y),QPointF(area.right(),y)); }
    if (points_.isEmpty()) return;
    double minX=points_[0].x(), maxX=minX, minY=points_[0].y(), maxY=minY;
    for (const auto &v: points_) { minX=qMin(minX,v.x()); maxX=qMax(maxX,v.x()); minY=qMin(minY,v.y()); maxY=qMax(maxY,v.y()); }
    const double spanX=qMax(0.01,maxX-minX), spanY=qMax(0.15,maxY-minY), midY=(minY+maxY)/2;
    QPolygonF shape;
    for (const auto &v: points_) shape << QPointF(area.left()+(v.x()-minX)/spanX*area.width(),area.center().y()-(v.y()-midY)/spanY*area.height()*0.75);
    p.setPen(QPen(QColor(dark?"#40c4ed":"#087ca8"),2)); p.drawPolyline(shape);
    p.restore();
    p.setPen(palette().color(QPalette::Text)); p.drawText(12,22,tr("Airfoil geometry"));
}

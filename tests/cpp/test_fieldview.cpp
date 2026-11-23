#include "fieldview.h"
#include <QApplication>
#include <QDataStream>
#include <QFile>
#include <QMouseEvent>
#include <QTemporaryDir>
#include <QWheelEvent>
#include <iostream>

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    QTemporaryDir temporary;
    QFile file(temporary.filePath("mesh_view.bin"));
    if (!file.open(QIODevice::WriteOnly)) return 1;
    QDataStream data(&file);
    data.setByteOrder(QDataStream::LittleEndian);
    data.setFloatingPointPrecision(QDataStream::SinglePrecision);
    data.writeRawData("SAFV1\0\0\0", 8);
    data << quint32(4) << quint32(1) << quint32(4) << quint32(0);
    data << float(-1) << float(2) << float(-1) << float(1) << float(0) << float(1);
    for (const auto &point : {QPointF(0,0),QPointF(1,0),QPointF(1,0.2),QPointF(0,0.2)})
        data << float(point.x()) << float(point.y());
    data << quint32(0) << quint32(1) << quint32(2) << quint32(3);
    for (const auto &point : {QPointF(0,0),QPointF(1,0),QPointF(1,0.2),QPointF(0,0.2)})
        data << float(point.x()) << float(point.y());
    file.close();
    FieldView view;
    view.resize(800, 500);
    if (!view.loadData(file.fileName())) return 2;
    view.show();
    app.processEvents();
    const QImage initial=view.grab().toImage();
    QWheelEvent wheel(QPointF(400,250),QPointF(400,250),QPoint(),QPoint(0,120),
                      Qt::NoButton,Qt::NoModifier,Qt::NoScrollPhase,false);
    QApplication::sendEvent(&view,&wheel);
    app.processEvents();
    if (initial==view.grab().toImage()) {
        std::cerr << "Wheel zoom did not change the rendered view\n";
        return 3;
    }
    const QImage zoomed=view.grab().toImage();
    QMouseEvent press(QEvent::MouseButtonPress,QPointF(400,250),QPointF(400,250),QPointF(400,250),Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);
    QMouseEvent move(QEvent::MouseMove,QPointF(460,280),QPointF(460,280),QPointF(460,280),Qt::NoButton,Qt::LeftButton,Qt::NoModifier);
    QMouseEvent release(QEvent::MouseButtonRelease,QPointF(460,280),QPointF(460,280),QPointF(460,280),Qt::LeftButton,Qt::NoButton,Qt::NoModifier);
    QApplication::sendEvent(&view,&press);
    QApplication::sendEvent(&view,&move);
    QApplication::sendEvent(&view,&release);
    app.processEvents();
    if (zoomed==view.grab().toImage()) {
        std::cerr << "Mouse drag did not change the rendered view\n";
        return 4;
    }
    view.resize(1000,600);
    app.processEvents();
    if (view.grab().size()!=QSize(1000,600)) return 5;
    return 0;
}

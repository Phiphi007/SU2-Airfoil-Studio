#pragma once
#include <QPointF>
#include <QVector>
#include <QWidget>

class HistoryView : public QWidget {
    Q_OBJECT
public:
    explicit HistoryView(QWidget *parent=nullptr);
    bool loadCsv(const QString &path);
    void resetView();
protected:
    void paintEvent(QPaintEvent *) override;
    void wheelEvent(QWheelEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
private:
    struct Sample { double iteration, residual, cl, cd; };
    QVector<Sample> samples_;
    double zoom_=1.0;
    double pan_=0.0;
    bool dragging_=false;
    double lastMouse_=0.0;
};

#pragma once
#include <QWidget>
#include <QPolygonF>
#include <QVector>

class FieldView : public QWidget {
    Q_OBJECT
public:
    explicit FieldView(QWidget *parent = nullptr);
    bool loadData(const QString &path);
    void resetView();
protected:
    void paintEvent(QPaintEvent *event) override;
    void wheelEvent(QWheelEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
private:
    struct Cell { QPolygonF polygon; float value = 0; };
    QVector<Cell> cells_;
    QPolygonF boundary_;
    QRectF bounds_;
    float minimum_ = 0, maximum_ = 1;
    bool hasField_ = false;
    double zoom_ = 1;
    QPointF pan_, lastMouse_;
    bool dragging_ = false;
    QColor fieldColor(double value) const;
};

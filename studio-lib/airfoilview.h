#pragma once
#include <QWidget>
#include <QVector>
#include <QPointF>
class AirfoilView : public QWidget {
    Q_OBJECT
public:
    explicit AirfoilView(QWidget *parent = nullptr);
    bool loadDat(const QString &path, QString *error);
    bool loadNaca4(const QString &designation, QString *error);
    bool saveDat(const QString &path, QString *error) const;
    void reset();
protected:
    void paintEvent(QPaintEvent *) override;
    void changeEvent(QEvent *event) override;
    void wheelEvent(QWheelEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
private:
    QVector<QPointF> points_;
    double zoom_ = 1.0;
    QPointF pan_;
    QPointF lastMouse_;
    bool dragging_ = false;
};

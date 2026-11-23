#include "historyview.h"
#include <QFile>
#include <QMouseEvent>
#include <QPainter>
#include <QTextStream>
#include <QWheelEvent>
#include <algorithm>
#include <cmath>

HistoryView::HistoryView(QWidget *parent):QWidget(parent) {setMinimumSize(480,300);}

bool HistoryView::loadCsv(const QString &path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly|QIODevice::Text)) return false;
    QTextStream stream(&file);
    if (stream.atEnd()) return false;
    auto clean=[](QString text){return text.trimmed().remove('"');};
    const QStringList header=stream.readLine().split(',');
    auto column=[&](const QString &name){for(int i=0;i<header.size();++i)if(clean(header[i])==name)return i;return -1;};
    const int iteration=column(QStringLiteral("Inner_Iter"));
    const int residual=column(QStringLiteral("rms[Rho]"));
    const int cl=column(QStringLiteral("CL")),cd=column(QStringLiteral("CD"));
    if (iteration<0 || residual<0 || cl<0 || cd<0) return false;
    const int required=std::max({iteration,residual,cl,cd});
    QVector<Sample> parsed;
    while (!stream.atEnd()) {
        const QStringList row=stream.readLine().split(',');
        if (row.size()<=required) continue;
        bool a,b,c,d;
        const double x=clean(row[iteration]).toDouble(&a),r=clean(row[residual]).toDouble(&b);
        const double lift=clean(row[cl]).toDouble(&c),drag=clean(row[cd]).toDouble(&d);
        if (a&&b&&c&&d&&std::isfinite(x)&&std::isfinite(r)&&std::isfinite(lift)&&std::isfinite(drag))
            parsed.append({x,r,lift,drag});
    }
    if (parsed.size()<2) return false;
    samples_=std::move(parsed);resetView();return true;
}

void HistoryView::resetView(){zoom_=1;pan_=0;update();}

void HistoryView::paintEvent(QPaintEvent *) {
    QPainter painter(this);painter.fillRect(rect(),palette().color(QPalette::Base));
    if (samples_.size()<2) return;
    painter.setRenderHint(QPainter::Antialiasing);
    const QColor ink=palette().color(QPalette::Text),grid=palette().color(QPalette::Mid);
    const QRectF top(65,42,width()-95,(height()-110)*0.47);
    const QRectF bottom(65,top.bottom()+48,width()-95,(height()-110)*0.47);
    const double maxX=samples_.last().iteration,minX=samples_.first().iteration;
    const double span=qMax(1.0,maxX-minX)/zoom_;
    const double left=minX+(maxX-minX-span)*0.5+pan_;
    const double right=left+span;
    auto chart=[&](const QRectF &plot, const QString &title, auto value, QColor color,
                   double fixedMin, double fixedMax) {
        double low=fixedMin,high=fixedMax;
        if (!(low<high)) {
            low=1e30;high=-1e30;
            for(const auto &sample:samples_) if(sample.iteration>=left&&sample.iteration<=right) {
                const double y=value(sample);low=qMin(low,y);high=qMax(high,y);
            }
            if (!(low<high)) {low-=1;high+=1;}
            const double margin=(high-low)*0.06;low-=margin;high+=margin;
        }
        painter.setPen(QPen(grid,1));
        for(int i=0;i<=4;++i) {
            const double y=plot.top()+plot.height()*i/4.0;
            painter.drawLine(QPointF(plot.left(),y),QPointF(plot.right(),y));
            painter.setPen(ink);painter.drawText(2,y+4,QString::number(high-(high-low)*i/4.0,'g',3));painter.setPen(QPen(grid,1));
        }
        painter.drawRect(plot);painter.setPen(ink);
        painter.drawText(plot.left(),plot.top()-10,title);
        painter.save();painter.setClipRect(plot);
        QPolygonF path;
        for(const auto &sample:samples_) {
            const double x=plot.left()+(sample.iteration-left)/span*plot.width();
            const double y=plot.bottom()-(value(sample)-low)/(high-low)*plot.height();
            path << QPointF(x,y);
        }
        painter.setPen(QPen(color,1.8));painter.drawPolyline(path);
        painter.restore();
    };
    chart(top,tr("Density residual (log10)"),[](const Sample &s){return s.residual;},QColor("#2878b5"),0,0);
    double low=1e30,high=-1e30;
    for(const auto &sample:samples_) if(sample.iteration>=left&&sample.iteration<=right) {
        low=std::min({low,sample.cl,sample.cd});high=std::max({high,sample.cl,sample.cd});
    }
    if(!(low<high)){low=-1;high=1;}
    const double margin=(high-low)*0.06;low-=margin;high+=margin;
    chart(bottom,tr("Force coefficients"),[](const Sample &s){return s.cl;},QColor("#b54f33"),low,high);
    chart(bottom,QString(),[](const Sample &s){return s.cd;},QColor("#3b9954"),low,high);
    painter.setPen(ink);painter.drawText(bottom.left(),height()-9,
        tr("Iteration: %1 to %2   CL (red)   CD (green)").arg(left,0,'f',0).arg(right,0,'f',0));
}

void HistoryView::wheelEvent(QWheelEvent *event) {
    zoom_=qBound(1.0,zoom_*std::pow(1.0015,event->angleDelta().y()),50.0);
    update();event->accept();
}
void HistoryView::mousePressEvent(QMouseEvent *event) {
    if(event->button()==Qt::LeftButton||event->button()==Qt::MiddleButton){dragging_=true;lastMouse_=event->position().x();setCursor(Qt::ClosedHandCursor);event->accept();}
}
void HistoryView::mouseMoveEvent(QMouseEvent *event) {
    if(!dragging_||samples_.isEmpty())return;
    const double span=(samples_.last().iteration-samples_.first().iteration)/zoom_;
    pan_-=(event->position().x()-lastMouse_)*span/qMax(1,width()-95);
    lastMouse_=event->position().x();update();event->accept();
}
void HistoryView::mouseReleaseEvent(QMouseEvent *event) {
    if(dragging_&&(event->button()==Qt::LeftButton||event->button()==Qt::MiddleButton)){dragging_=false;unsetCursor();event->accept();}
}

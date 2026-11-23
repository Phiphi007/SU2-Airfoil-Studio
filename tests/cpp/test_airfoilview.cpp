#include "airfoilview.h"
#include <QApplication>
#include <QFile>
#include <QTemporaryDir>
#include <QTextStream>
#include <cmath>
#include <iostream>

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    AirfoilView view;
    QString error;
    if (!view.loadNaca4(QStringLiteral("2412"), &error)) return 1;
    QTemporaryDir temporary;
    const QString path=temporary.filePath(QStringLiteral("naca2412.dat"));
    if (!view.saveDat(path, &error)) return 2;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) return 3;
    QTextStream input(&file);
    int count=0;
    double upperAtMid=0, lowerAtMid=0;
    while (!input.atEnd()) {
        const QStringList fields=input.readLine().split(' ',Qt::SkipEmptyParts);
        if (fields.size()!=2) continue;
        const double x=fields[0].toDouble(), y=fields[1].toDouble();
        if (count<101 && std::abs(x-0.5)<0.02) upperAtMid=y;
        if (count>=101 && std::abs(x-0.5)<0.02) lowerAtMid=y;
        ++count;
    }
    if (count!=201 || upperAtMid<0.07 || lowerAtMid>0.0) {
        std::cerr << "NACA2412 geometry was not exported as expected\n";
        return 4;
    }
    if (view.loadNaca4(QStringLiteral("2012"), &error)) return 5;
    return 0;
}

#pragma once
#include <QByteArray>
#include <QString>
struct RunSettings {
    QString mode;
    QString airfoil;
    QString outputDirectory;
    int surfacePoints;
    double refinement;
    double mach;
    double angleOfAttack;
    double reynolds;
    int iterations;
    QString solver;
};
QByteArray encodeRequest(const RunSettings &settings);

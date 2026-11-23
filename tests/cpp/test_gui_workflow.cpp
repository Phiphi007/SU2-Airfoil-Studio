#include "mainwindow.h"
#include <QAction>
#include <QApplication>
#include <QDir>
#include <QDoubleSpinBox>
#include <QComboBox>
#include <QElapsedTimer>
#include <QFile>
#include <QInputDialog>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QSpinBox>
#include <QTabWidget>
#include <QTemporaryDir>
#include <QThread>
#include <QTimer>
#include <iostream>

int main(int argc,char **argv) {
    QApplication app(argc,argv);
    QTemporaryDir temporary;
    if (!temporary.isValid()) return 1;
    qputenv("XDG_CONFIG_HOME", temporary.path().toUtf8());
    MainWindow window;
    window.show();
    const auto edits=window.findChildren<QLineEdit*>();
    QLineEdit *workspace=nullptr;
    for (auto *edit:edits) if(edit->minimumWidth()>=300) workspace=edit;
    if(!workspace) return 2;
    workspace->setText(temporary.path());
    auto *naca=window.findChild<QAction*>("NacaAction");
    if(!naca) return 3;
    QTimer::singleShot(0,[]{
        auto *dialog=qobject_cast<QInputDialog*>(QApplication::activeModalWidget());
        if(dialog){dialog->setTextValue(QStringLiteral("4412"));dialog->accept();}
    });
    naca->trigger();
    bool selected=false;
    for(auto *label:window.findChildren<QLabel*>()) if(label->text()==QStringLiteral("NACA 4412")) selected=true;
    if(!selected) return 4;
    auto findAction=[&](const QString &name)->QAction* {
        for(auto *action:window.findChildren<QAction*>()) if(action->text()==name) return action;
        return nullptr;
    };
    auto *mesh=findAction(QStringLiteral("Generate mesh"));
    if(!mesh) return 5;
    auto *refinement=window.findChild<QDoubleSpinBox*>("MeshRefinement");
    if(!refinement)return 11;
    refinement->setValue(0.1);
    mesh->trigger();
    QString casePath;
    QElapsedTimer timer;timer.start();
    while(timer.elapsed()<60000) {
        app.processEvents();
        const QStringList cases=QDir(temporary.path()).entryList({QStringLiteral("case-*")},QDir::Dirs|QDir::NoDotAndDotDot);
        if(!cases.isEmpty()) {
            casePath=QDir(temporary.path()).filePath(cases.first());
            if(QFile::exists(casePath+QStringLiteral("/api_result.json")) && mesh->isEnabled())break;
        }
        QThread::msleep(25);
    }
    if(casePath.isEmpty()||!mesh->isEnabled()||!QFile::exists(casePath+QStringLiteral("/mesh_view.bin"))) {
        std::cerr << "GUI mesh action did not generate a native mesh view\n";return 6;
    }
    QFile result(casePath+QStringLiteral("/api_result.json"));
    if(!result.open(QIODevice::ReadOnly)||!QJsonDocument::fromJson(result.readAll()).object().value("ok").toBool())return 7;
    QFile request(casePath+QStringLiteral("/case_request.json"));
    if(!request.open(QIODevice::ReadOnly))return 8;
    const QJsonObject saved=QJsonDocument::fromJson(request.readAll()).object();
    if(saved.value("airfoil").toString()!=QStringLiteral("builtin://naca4412"))return 9;
    auto *tabs=window.findChild<QTabWidget*>();
    if(!tabs||tabs->currentIndex()!=1||!tabs->isTabEnabled(1))return 10;
    auto *solver=window.findChild<QComboBox*>("Solver");
    auto *iterations=window.findChild<QSpinBox*>("Iterations");
    auto *solve=findAction(QStringLiteral("Run CFD"));
    if(!solver||!iterations||!solve)return 12;
    solver->setCurrentText(QStringLiteral("EULER"));
    iterations->setValue(30);
    solve->trigger();
    QString solveCase;
    timer.restart();
    while(timer.elapsed()<90000) {
        app.processEvents();
        const QStringList cases=QDir(temporary.path()).entryList({QStringLiteral("case-*")},QDir::Dirs|QDir::NoDotAndDotDot);
        for(const QString &name:cases) {
            const QString candidate=QDir(temporary.path()).filePath(name);
            if(candidate==casePath||!QFile::exists(candidate+QStringLiteral("/api_result.json")))continue;
            QFile response(candidate+QStringLiteral("/api_result.json"));
            if(response.open(QIODevice::ReadOnly) && QJsonDocument::fromJson(response.readAll()).object().value("mode")==QStringLiteral("solve"))
                solveCase=candidate;
        }
        if(!solveCase.isEmpty()&&solve->isEnabled())break;
        QThread::msleep(25);
    }
    if(solveCase.isEmpty()||!solve->isEnabled()||!QFile::exists(solveCase+QStringLiteral("/flow_view.bin"))||!tabs->isTabEnabled(3)) {
        std::cerr << "GUI solve action did not generate a native flow and convergence view\n";return 13;
    }
    QFile solveResult(solveCase+QStringLiteral("/api_result.json"));
    if(!solveResult.open(QIODevice::ReadOnly))return 14;
    const QJsonObject solved=QJsonDocument::fromJson(solveResult.readAll()).object();
    if(!solved.value("ok").toBool()||!QFile::exists(solveCase+QStringLiteral("/history.csv")))return 15;
    QFile solveRequest(solveCase+QStringLiteral("/case_request.json"));
    if(!solveRequest.open(QIODevice::ReadOnly))return 16;
    const QJsonObject solveSettings=QJsonDocument::fromJson(solveRequest.readAll()).object();
    const QJsonObject parameters=solveSettings.value("parameters").toObject();
    if(parameters.value("solver").toString()!=QStringLiteral("EULER")||parameters.value("iterations").toInt()!=30)return 17;
    window.close();
    return 0;
}

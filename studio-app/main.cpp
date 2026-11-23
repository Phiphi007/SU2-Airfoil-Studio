#include "mainwindow.h"
#include "theme.h"
#include <QApplication>
#include <QCoreApplication>
#include <QStyleFactory>
#include <QPalette>
#include <QColor>
#include <QFont>
#include <QSettings>
#include <QCommandLineParser>
#include <QTimer>
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    QCoreApplication::setOrganizationName("SU2 Airfoil Studio");
    QCoreApplication::setApplicationName("SU2 Airfoil Studio");
    StudioTheme::apply(QSettings().value("theme", "light").toString());
    app.setFont(QFont("Noto Sans", 10));
    QCommandLineParser parser;
    parser.setApplicationDescription("SU2 Airfoil Studio");
    parser.addHelpOption();
    parser.addOption({"open-case", "Open a completed result case directory.", "directory"});
    parser.addOption({"screenshot", "Save a screenshot after the window opens.", "file"});
    parser.addOption({"tab", "Select a work tab (0 airfoil, 1 mesh, 2 flow, 3 convergence).", "index"});
    parser.process(app);
    MainWindow window;
    window.show();
    if (parser.isSet("open-case")) window.openCase(parser.value("open-case"));
    if (parser.isSet("tab")) window.selectTab(parser.value("tab").toInt());
    if (parser.isSet("screenshot")) {
        const QString path=parser.value("screenshot");
        QTimer::singleShot(800,&window,[&window,path,&app] {
            app.exit(window.grab().save(path) ? 0 : 1);
        });
    }
    return app.exec();
}

#pragma once
#include <QMainWindow>
#include <QProcess>
#include <QTranslator>
#include <QVector>
#include <QPointF>
class QDoubleSpinBox;
class QSpinBox;
class QLineEdit;
class QPlainTextEdit;
class QTreeWidget;
class QLabel;
class QAction;
class QComboBox;
class QTabWidget;
class AirfoilView;
class FieldView;
class HistoryView;
class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    MainWindow();
    bool openCase(const QString &directory);
    bool selectTab(int index);
protected:
    void closeEvent(QCloseEvent *event) override;
private:
    void buildUi();
    void retranslate();
    void start(const QString &mode);
    void finish(int code, QProcess::ExitStatus status);
    void chooseAirfoil();
    void exportAirfoil();
    void chooseDirectory();
    void chooseCase();
    void chooseLanguage(int index);
    void showPreferences();
    void sendSolverControl(const QString &command);
    QString python() const;
    QString sourceRoot() const;
    QProcess process_;
    QTranslator translator_;
    QString airfoil_ = "builtin://naca0012";
    QString currentOutput_;
    QString currentMode_;
    QString currentCase_;
    bool solverPaused_ = false;
    QLineEdit *directory_ = nullptr;
    QLineEdit *su2Path_ = nullptr;
    QLineEdit *gmshPath_ = nullptr;
    QPlainTextEdit *log_ = nullptr;
    QTreeWidget *project_ = nullptr;
    AirfoilView *view_ = nullptr;
    QTabWidget *tabs_ = nullptr;
    FieldView *meshView_ = nullptr;
    FieldView *contourView_ = nullptr;
    HistoryView *historyView_ = nullptr;
    QLabel *summary_ = nullptr;
    QLabel *airfoilLabel_ = nullptr;
    QComboBox *language_ = nullptr;
    QComboBox *solver_ = nullptr;
    QDoubleSpinBox *mach_ = nullptr, *aoa_ = nullptr, *reynolds_ = nullptr, *refinement_ = nullptr;
    QSpinBox *points_ = nullptr, *iterations_ = nullptr;
    QAction *openAction_ = nullptr, *meshAction_ = nullptr, *solveAction_ = nullptr, *stopAction_ = nullptr;
    QAction *exportAction_ = nullptr;
    QAction *pauseAction_ = nullptr, *stopAfterSaveAction_ = nullptr;
    QAction *optimizeAction_ = nullptr;
};

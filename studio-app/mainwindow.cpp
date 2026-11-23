#include "backendrequest.h"
#include "airfoilview.h"
#include "fieldview.h"
#include "historyview.h"
#include "mainwindow.h"
#include "theme.h"
#include <QAction>
#include <QApplication>
#include <QCloseEvent>
#include <QComboBox>
#include <QDir>
#include <QDockWidget>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFontDatabase>
#include <QFormLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QInputDialog>
#include <QLabel>
#include <QLineEdit>
#include <QMenuBar>
#include <QMessageBox>
#include <QPainter>
#include <QPlainTextEdit>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QCoreApplication>
#include <QFormLayout>
#include <QSettings>
#include <QSaveFile>
#include <QSpinBox>
#include <QStyle>
#include <QStandardPaths>
#include <QStatusBar>
#include <QTextStream>
#include <QToolBar>
#include <QTabWidget>
#include <QTreeWidget>
#include <QVBoxLayout>
#include <QUuid>
#include <cmath>

MainWindow::MainWindow() {
    buildUi(); retranslate();
    QSettings settings;
    restoreGeometry(settings.value("geometry").toByteArray());
    restoreState(settings.value("state").toByteArray());
    directory_->setText(settings.value("directory",QDir::homePath()+"/SU2-Cases").toString());
    su2Path_->setText(settings.value("su2Executable").toString());
    gmshPath_->setText(settings.value("gmshPythonPath").toString());
    chooseLanguage(settings.value("language","en").toString()==QStringLiteral("zh_CN")?1:0);
    connect(&process_,&QProcess::readyReadStandardError,this,[this] { log_->appendPlainText(QString::fromUtf8(process_.readAllStandardError()).trimmed()); });
    connect(&process_,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,&MainWindow::finish);
    connect(&process_,&QProcess::errorOccurred,this,[this](QProcess::ProcessError) { log_->appendPlainText(process_.errorString()); });
}
QString MainWindow::sourceRoot() const { const QString configured=qEnvironmentVariable("SU2_STUDIO_ROOT"); return configured.isEmpty() ? QStringLiteral(STUDIO_SOURCE_DIR) : configured; }
QString MainWindow::python() const {
    const QString configured=qEnvironmentVariable("SU2_STUDIO_PYTHON");
    if (!configured.isEmpty()) return configured;
#ifdef Q_OS_WIN
    return QCoreApplication::applicationDirPath()+"/runtime/python/Scripts/python.exe";
#else
    return QCoreApplication::applicationDirPath()+"/runtime/python/bin/python";
#endif
}
void MainWindow::buildUi() {
    setMinimumSize(1000,650); resize(1440,900); setDockNestingEnabled(true);
    openAction_=new QAction(this); openAction_->setShortcut(QKeySequence::Open); connect(openAction_,&QAction::triggered,this,&MainWindow::chooseAirfoil);
    exportAction_=new QAction(this);exportAction_->setShortcut(QKeySequence::Save);connect(exportAction_,&QAction::triggered,this,&MainWindow::exportAirfoil);
    meshAction_=new QAction(this); meshAction_->setShortcut(Qt::Key_F5); connect(meshAction_,&QAction::triggered,this,[this]{start("mesh");});
    solveAction_=new QAction(this); solveAction_->setShortcut(Qt::Key_F6); connect(solveAction_,&QAction::triggered,this,[this]{start("solve");});
    optimizeAction_=new QAction(this); connect(optimizeAction_,&QAction::triggered,this,[this]{start("optimize");});
    openAction_->setIcon(style()->standardIcon(QStyle::SP_DialogOpenButton));
    meshAction_->setIcon(style()->standardIcon(QStyle::SP_BrowserReload));
    solveAction_->setIcon(style()->standardIcon(QStyle::SP_MediaPlay));
    stopAction_=new QAction(this);stopAction_->setIcon(style()->standardIcon(QStyle::SP_MediaStop)); stopAction_->setEnabled(false); connect(stopAction_,&QAction::triggered,this,[this]{
        if (currentMode_==QStringLiteral("solve")) sendSolverControl(QStringLiteral("stop_now"));
        else process_.kill();
    });
    pauseAction_=new QAction(this);pauseAction_->setEnabled(false);connect(pauseAction_,&QAction::triggered,this,[this]{
        sendSolverControl(solverPaused_?QStringLiteral("resume"):QStringLiteral("pause"));
        solverPaused_=!solverPaused_;pauseAction_->setText(solverPaused_?tr("Resume CFD"):tr("Pause CFD"));
    });
    stopAfterSaveAction_=new QAction(this);stopAfterSaveAction_->setEnabled(false);
    connect(stopAfterSaveAction_,&QAction::triggered,this,[this]{sendSolverControl(QStringLiteral("stop_after_save"));stopAfterSaveAction_->setEnabled(false);});
    auto *file=menuBar()->addMenu(QString()); file->setObjectName("fileMenu"); file->addActions({openAction_,exportAction_});
    auto *nacaAction=file->addAction(QString(),this,[this] {
        bool accepted=false;
        const QString designation=QInputDialog::getText(this,tr("NACA four-digit airfoil"),
            tr("Designation"),QLineEdit::Normal,QStringLiteral("2412"),&accepted).trimmed();
        if (!accepted) return;
        QString error;
        if (!view_->loadNaca4(designation,&error)) {
            QMessageBox::warning(this,tr("Invalid airfoil"),error);return;
        }
        airfoil_=QStringLiteral("builtin://naca")+designation;
        airfoilLabel_->setText(QStringLiteral("NACA ")+designation);
        tabs_->setCurrentIndex(0);
        log_->appendPlainText(tr("Selected NACA %1").arg(designation));
    });
    nacaAction->setObjectName("NacaAction");
    auto *openCaseAction=file->addAction(QString(),this,&MainWindow::chooseCase);openCaseAction->setObjectName("OpenCaseAction");
    file->addSeparator(); auto *exitAction=file->addAction(tr("Exit"),this,&QWidget::close);exitAction->setObjectName("ExitAction");
    auto *options=menuBar()->addMenu(QString());options->setObjectName("optionsMenu");auto *preferences=options->addAction(QString(),this,&MainWindow::showPreferences);preferences->setObjectName("PreferencesAction");
    auto *run=menuBar()->addMenu(QString()); run->setObjectName("runMenu"); run->addActions({meshAction_,solveAction_,optimizeAction_});run->addSeparator();run->addActions({pauseAction_,stopAfterSaveAction_,stopAction_});
    auto *viewMenu=menuBar()->addMenu(QString()); viewMenu->setObjectName("viewMenu"); auto *resetAction=viewMenu->addAction(tr("Reset layout"),this,[this]{ resize(1440,900); });resetAction->setObjectName("ResetAction");
    auto *help=menuBar()->addMenu(QString());help->setObjectName("helpMenu");auto *about=help->addAction(QString(),this,[this]{QMessageBox::about(this,tr("About SU2 Airfoil Studio"),tr("SU2 Airfoil Studio — Qt6/C++ desktop\nVersion 2.0.0"));});about->setObjectName("AboutAction");
    auto *aboutQt=help->addAction(QString(),qApp,&QApplication::aboutQt);aboutQt->setObjectName("AboutQtAction");
    auto *bar=addToolBar(QString()); bar->setObjectName("MainToolbar"); bar->setMovable(false); bar->addActions({openAction_,exportAction_,meshAction_,solveAction_,stopAction_});
    auto *browse=bar->addAction(tr("Browse workspace"));browse->setObjectName("BrowseAction"); connect(browse,&QAction::triggered,this,&MainWindow::chooseDirectory);
    directory_=new QLineEdit; directory_->setMinimumWidth(300); bar->addWidget(directory_);
    tabs_=new QTabWidget;view_=new AirfoilView;tabs_->addTab(view_,QString());
    meshView_=new FieldView;contourView_=new FieldView;
    tabs_->addTab(meshView_,QString());tabs_->addTab(contourView_,QString());
    historyView_=new HistoryView;tabs_->addTab(historyView_,QString());
    tabs_->setTabEnabled(1,false);tabs_->setTabEnabled(2,false);tabs_->setTabEnabled(3,false);
    setCentralWidget(tabs_);
    auto *projectDock=new QDockWidget(this); projectDock->setObjectName("ProjectDock"); project_=new QTreeWidget; project_->setHeaderHidden(true); projectDock->setWidget(project_); addDockWidget(Qt::LeftDockWidgetArea,projectDock);
    auto *propertyDock=new QDockWidget(this); propertyDock->setObjectName("PropertiesDock"); auto *property=new QWidget; auto *form=new QFormLayout(property);
    airfoilLabel_=new QLabel("NACA 0012"); form->addRow(tr("Airfoil"),airfoilLabel_);
    auto dbl=[&](double v,double low,double high,int decimals){auto *w=new QDoubleSpinBox;w->setRange(low,high);w->setDecimals(decimals);w->setValue(v);return w;};
    points_=new QSpinBox;points_->setRange(20,1000);points_->setValue(100);form->addRow(tr("Surface points"),points_);
    refinement_=dbl(1,0.05,10,2);refinement_->setObjectName("MeshRefinement");form->addRow(tr("Mesh refinement"),refinement_);
    mach_=dbl(0.15,0.001,5,3);form->addRow(tr("Mach"),mach_);
    aoa_=dbl(2,-30,30,2);form->addRow(tr("Angle of attack (deg)"),aoa_);
    reynolds_=dbl(3000000,1,1e10,0);form->addRow(tr("Reynolds number"),reynolds_);
    iterations_=new QSpinBox;iterations_->setObjectName("Iterations");iterations_->setRange(1,1000000);iterations_->setValue(1000);form->addRow(tr("Iterations"),iterations_);
    solver_=new QComboBox;solver_->setObjectName("Solver");solver_->addItems({QStringLiteral("RANS"),QStringLiteral("EULER")});form->addRow(tr("Solver"),solver_);
    su2Path_=new QLineEdit(this);su2Path_->hide();gmshPath_=new QLineEdit(this);gmshPath_->hide();
    propertyDock->setWidget(property);addDockWidget(Qt::RightDockWidgetArea,propertyDock);
    auto *outputDock=new QDockWidget(this);outputDock->setObjectName("OutputDock");log_=new QPlainTextEdit;log_->setReadOnly(true);
    const int fontId=QFontDatabase::addApplicationFont(QStringLiteral(":/fonts/JetBrainsMono-Regular.ttf"));
    const QStringList families=QFontDatabase::applicationFontFamilies(fontId);
    QFont outputFont(families.isEmpty()?QStringLiteral("JetBrains Mono"):families.first());
    outputFont.setStyleHint(QFont::Monospace);outputFont.setPointSize(10);log_->setFont(outputFont);
    outputDock->setWidget(log_);addDockWidget(Qt::BottomDockWidgetArea,outputDock);
    summary_=new QLabel;statusBar()->addPermanentWidget(summary_);
}
void MainWindow::retranslate() {
    setWindowTitle(tr("SU2 Airfoil Studio"));
    openAction_->setText(tr("Open airfoil…"));exportAction_->setText(tr("Export airfoil…"));meshAction_->setText(tr("Generate mesh"));solveAction_->setText(tr("Run CFD"));optimizeAction_->setText(tr("Optimize airfoil…"));stopAction_->setText(tr("Stop now"));pauseAction_->setText(solverPaused_?tr("Resume CFD"):tr("Pause CFD"));stopAfterSaveAction_->setText(tr("Stop after save"));
    findChild<QMenu*>("fileMenu")->setTitle(tr("File"));findChild<QMenu*>("runMenu")->setTitle(tr("Run"));findChild<QMenu*>("viewMenu")->setTitle(tr("View"));
    findChild<QDockWidget*>("ProjectDock")->setWindowTitle(tr("Project"));findChild<QDockWidget*>("PropertiesDock")->setWindowTitle(tr("Properties"));findChild<QDockWidget*>("OutputDock")->setWindowTitle(tr("Output"));
    findChild<QAction*>("ExitAction")->setText(tr("Exit"));
    findChild<QAction*>("OpenCaseAction")->setText(tr("Open result case…"));
    findChild<QAction*>("NacaAction")->setText(tr("NACA four-digit airfoil…"));
    findChild<QAction*>("ResetAction")->setText(tr("Reset layout"));
    findChild<QMenu*>("optionsMenu")->setTitle(tr("Options"));findChild<QAction*>("PreferencesAction")->setText(tr("Preferences…"));
    findChild<QMenu*>("helpMenu")->setTitle(tr("Help"));findChild<QAction*>("AboutAction")->setText(tr("About SU2 Airfoil Studio"));findChild<QAction*>("AboutQtAction")->setText(tr("About Qt"));
    findChild<QAction*>("BrowseAction")->setText(tr("Browse workspace"));
    tabs_->setTabText(0,tr("Airfoil"));tabs_->setTabText(1,tr("Mesh"));tabs_->setTabText(2,tr("Flow contour"));
    tabs_->setTabText(3,tr("Convergence"));
    auto *form=qobject_cast<QFormLayout*>(findChild<QDockWidget*>("PropertiesDock")->widget()->layout());
    form->labelForField(airfoilLabel_)->setProperty("text",tr("Airfoil"));
    form->labelForField(points_)->setProperty("text",tr("Surface points"));
    form->labelForField(refinement_)->setProperty("text",tr("Mesh refinement"));
    form->labelForField(mach_)->setProperty("text",tr("Mach"));
    form->labelForField(aoa_)->setProperty("text",tr("Angle of attack (deg)"));
    form->labelForField(reynolds_)->setProperty("text",tr("Reynolds number"));
    form->labelForField(iterations_)->setProperty("text",tr("Iterations"));
    form->labelForField(solver_)->setProperty("text",tr("Solver"));
    view_->update();
    project_->clear();auto *root=new QTreeWidgetItem(project_,QStringList(tr("Airfoil study")));new QTreeWidgetItem(root,QStringList(QFileInfo(airfoil_).fileName().isEmpty()?tr("NACA 0012"):QFileInfo(airfoil_).fileName()));root->setExpanded(true);
    summary_->setText(process_.state()==QProcess::NotRunning?tr("Ready"):tr("Running"));
}
void MainWindow::chooseLanguage(int index) {
    qApp->removeTranslator(&translator_);
    if (index==1) {
        const QString path=QCoreApplication::applicationDirPath()+"/studio_zh_CN.qm";
        if (translator_.load(path)) qApp->installTranslator(&translator_);
    }
    retranslate();
    QSettings().setValue("language",index==1?"zh_CN":"en");
}
void MainWindow::showPreferences() {
    QDialog dialog(this);dialog.setWindowTitle(tr("Preferences"));
    auto *layout=new QVBoxLayout(&dialog);auto *form=new QFormLayout;
    auto *language=new QComboBox;language->addItem(tr("English"),"en");language->addItem(tr("Chinese (Simplified)"),"zh_CN");
    language->setCurrentIndex(QSettings().value("language","en").toString()==QStringLiteral("zh_CN")?1:0);
    auto *theme=new QComboBox;theme->addItem(tr("Light"),"light");theme->addItem(tr("Dark"),"dark");
    theme->setCurrentIndex(QSettings().value("theme","light").toString()==QStringLiteral("dark")?1:0);
    auto *su2=new QLineEdit(su2Path_->text());auto *gmsh=new QLineEdit(gmshPath_->text());
    form->addRow(tr("Language"),language);form->addRow(tr("Appearance"),theme);
    form->addRow(tr("SU2 executable"),su2);form->addRow(tr("Gmsh Python path"),gmsh);layout->addLayout(form);
    auto *buttons=new QDialogButtonBox(QDialogButtonBox::Ok|QDialogButtonBox::Cancel);layout->addWidget(buttons);
    connect(buttons,&QDialogButtonBox::accepted,&dialog,&QDialog::accept);
    connect(buttons,&QDialogButtonBox::rejected,&dialog,&QDialog::reject);
    if(dialog.exec()!=QDialog::Accepted) return;
    QSettings settings;settings.setValue("theme",theme->currentData().toString());
    StudioTheme::apply(theme->currentData().toString());
    su2Path_->setText(su2->text().trimmed());gmshPath_->setText(gmsh->text().trimmed());
    chooseLanguage(language->currentIndex());
}
void MainWindow::chooseAirfoil() {
    const QString path=QFileDialog::getOpenFileName(this,tr("Open airfoil"),QString(),tr("Airfoil DAT (*.dat);;All files (*)"));
    if (path.isEmpty()) return;
    QString error; if (!view_->loadDat(path,&error)) {QMessageBox::warning(this,tr("Invalid airfoil"),error);return;}
    airfoil_=path;airfoilLabel_->setText(QFileInfo(path).fileName());retranslate();
}
void MainWindow::exportAirfoil() {
    const QString path=QFileDialog::getSaveFileName(this,tr("Export airfoil"),directory_->text()+"/airfoil.dat",tr("Airfoil DAT (*.dat)"));
    if(path.isEmpty()) return;
    QString error;if(!view_->saveDat(path,&error)) QMessageBox::warning(this,tr("Export failed"),error);
    else log_->appendPlainText(tr("Exported airfoil: %1").arg(path));
}
void MainWindow::chooseDirectory() {const QString path=QFileDialog::getExistingDirectory(this,tr("Choose workspace"),directory_->text());if(!path.isEmpty())directory_->setText(path);}
void MainWindow::chooseCase() {
    const QString path=QFileDialog::getExistingDirectory(this,tr("Open result case"),directory_->text());
    if (!path.isEmpty() && !openCase(path)) QMessageBox::warning(this,tr("Result unavailable"),tr("This case has no native mesh or flow view data."));
}
bool MainWindow::openCase(const QString &directory) {
    const QDir caseDir(directory);
    QFile requestFile(caseDir.filePath(QStringLiteral("case_request.json")));
    if (requestFile.open(QIODevice::ReadOnly)) {
        const QJsonObject request=QJsonDocument::fromJson(requestFile.readAll()).object();
        const QString foil=request.value(QStringLiteral("airfoil")).toString();
        if (!foil.isEmpty()) {
            airfoil_=foil;
            QString geometryError;
            if (foil.startsWith(QStringLiteral("builtin://naca")))
                view_->loadNaca4(foil.right(4),&geometryError);
            else if (QFileInfo::exists(foil)) view_->loadDat(foil,&geometryError);
            airfoilLabel_->setText(foil.startsWith(QStringLiteral("builtin://"))
                ? foil.mid(QStringLiteral("builtin://").size()).toUpper() : QFileInfo(foil).fileName());
        }
        const QJsonObject parameters=request.value(QStringLiteral("parameters")).toObject();
        if (parameters.contains(QStringLiteral("surface_points"))) points_->setValue(parameters.value(QStringLiteral("surface_points")).toInt());
        if (parameters.contains(QStringLiteral("global_refinement"))) refinement_->setValue(parameters.value(QStringLiteral("global_refinement")).toDouble());
        if (parameters.contains(QStringLiteral("mach"))) mach_->setValue(parameters.value(QStringLiteral("mach")).toDouble());
        if (parameters.contains(QStringLiteral("aoa"))) aoa_->setValue(parameters.value(QStringLiteral("aoa")).toDouble());
        if (parameters.contains(QStringLiteral("reynolds"))) reynolds_->setValue(parameters.value(QStringLiteral("reynolds")).toDouble());
        if (parameters.contains(QStringLiteral("iterations"))) iterations_->setValue(parameters.value(QStringLiteral("iterations")).toInt());
        if (parameters.contains(QStringLiteral("solver"))) solver_->setCurrentText(parameters.value(QStringLiteral("solver")).toString());
    }
    const bool hasMesh=meshView_->loadData(caseDir.filePath(QStringLiteral("mesh_view.bin")));
    const bool hasContour=contourView_->loadData(caseDir.filePath(QStringLiteral("flow_view.bin")));
    const bool hasHistory=historyView_->loadCsv(caseDir.filePath(QStringLiteral("history.csv")));
    if (!hasMesh && !hasContour && !hasHistory) return false;
    tabs_->setTabEnabled(1,hasMesh);tabs_->setTabEnabled(2,hasContour);tabs_->setTabEnabled(3,hasHistory);
    tabs_->setCurrentIndex(hasContour?2:1);
    project_->clear();auto *root=new QTreeWidgetItem(project_,QStringList(QFileInfo(directory).fileName()));
    if (hasMesh) {
        new QTreeWidgetItem(root,QStringList(QStringLiteral("mesh.su2")));
        new QTreeWidgetItem(root,QStringList(QStringLiteral("mesh_view.bin")));
    }
    if (hasContour) {
        new QTreeWidgetItem(root,QStringList(QStringLiteral("flow.vtu")));
        new QTreeWidgetItem(root,QStringList(QStringLiteral("flow_view.bin")));
    }
    if (hasHistory) new QTreeWidgetItem(root,QStringList(QStringLiteral("history.csv")));
    currentCase_=caseDir.absolutePath();
    root->setExpanded(true);
    QFile resultFile(QDir(directory).filePath(QStringLiteral("api_result.json")));
    if (resultFile.open(QIODevice::ReadOnly)) {
        const QJsonObject result=QJsonDocument::fromJson(resultFile.readAll()).object();
        const QJsonObject values=result.value(QStringLiteral("last_values")).toObject();
        log_->appendPlainText(tr("Loaded case: %1").arg(QFileInfo(directory).fileName()));
        if (hasContour) {
            log_->appendPlainText(tr("Iterations: %1 | CL: %2 | CD: %3")
                .arg(values.value(QStringLiteral("Inner_Iter")).toDouble()+1,0,'f',0)
                .arg(values.value(QStringLiteral("CL")).toDouble(),0,'f',4)
                .arg(values.value(QStringLiteral("CD")).toDouble(),0,'f',4));
            log_->appendPlainText(tr("Density residual (log10): %1 | Target met: %2")
                .arg(values.value(QStringLiteral("rms[Rho]")).toDouble(),0,'f',3)
                .arg(result.value(QStringLiteral("residual_target_met")).toBool()?tr("yes"):tr("no")));
        }
    }
    summary_->setText(tr("Result loaded"));
    return true;
}
bool MainWindow::selectTab(int index) {
    if (index<0 || index>=tabs_->count() || !tabs_->isTabEnabled(index)) return false;
    tabs_->setCurrentIndex(index);return true;
}
void MainWindow::sendSolverControl(const QString &command) {
    if (currentMode_!=QStringLiteral("solve") || currentOutput_.isEmpty() || process_.state()==QProcess::NotRunning) return;
    QSaveFile file(currentOutput_+QStringLiteral("/.solver_control.json"));
    if (!file.open(QIODevice::WriteOnly|QIODevice::Text)) {log_->appendPlainText(file.errorString());return;}
    const QJsonObject payload{{QStringLiteral("serial"),QUuid::createUuid().toString(QUuid::WithoutBraces)},
                              {QStringLiteral("command"),command}};
    file.write(QJsonDocument(payload).toJson(QJsonDocument::Compact));
    if (!file.commit()) {log_->appendPlainText(file.errorString());return;}
    log_->appendPlainText(tr("Solver command: %1").arg(command));
}
void MainWindow::start(const QString &mode) {
    if (process_.state()!=QProcess::NotRunning) return;
    QDir root(directory_->text());if(!root.mkpath(".")){QMessageBox::warning(this,tr("Workspace error"),tr("Cannot create workspace."));return;}
    currentOutput_=root.absoluteFilePath("case-"+QUuid::createUuid().toString(QUuid::WithoutBraces));
    currentMode_=mode;solverPaused_=false;
    QByteArray requestBytes;
    if (mode==QStringLiteral("optimize")) {
        if (currentCase_.isEmpty()) {QMessageBox::warning(this,tr("Optimization unavailable"),tr("Open a completed CFD case first."));return;}
        bool accepted=false;
        const QString method=QInputDialog::getItem(this,tr("Optimization method"),tr("Parameterization"),
            {QStringLiteral("cst"),QStringLiteral("bce"),QStringLiteral("hybrid"),QStringLiteral("relay")},0,false,&accepted);
        if (!accepted) return;
        const int steps=QInputDialog::getInt(this,tr("Optimization attempts"),tr("Attempts"),3,1,100,1,&accepted);
        if (!accepted) return;
        const QJsonObject request{{QStringLiteral("api_version"),1},{QStringLiteral("mode"),mode},
            {QStringLiteral("case_dir"),currentCase_},{QStringLiteral("output_dir"),currentOutput_},
            {QStringLiteral("method"),method},{QStringLiteral("steps"),steps}};
        requestBytes=QJsonDocument(request).toJson(QJsonDocument::Compact);
    } else {
        RunSettings request{mode,airfoil_,currentOutput_,points_->value(),refinement_->value(),mach_->value(),aoa_->value(),reynolds_->value(),iterations_->value(),solver_->currentText()};
        requestBytes=encodeRequest(request);
    }
    log_->appendPlainText(tr("Starting %1 in %2").arg(mode,currentOutput_));
    QProcessEnvironment environment=QProcessEnvironment::systemEnvironment();
    if(!su2Path_->text().trimmed().isEmpty()) environment.insert("SU2AUTOFOIL_SU2_EXECUTABLE",su2Path_->text().trimmed());
    if(!gmshPath_->text().trimmed().isEmpty())
        environment.insert("SU2_STUDIO_GMSH_PYTHON_PATH",gmshPath_->text().trimmed());
    process_.setProcessEnvironment(environment);
    QString program=python();
    QStringList arguments{sourceRoot()+"/portable_api.py","run"};
    if (qEnvironmentVariableIsEmpty("SU2_STUDIO_PYTHON")) {
#ifdef Q_OS_WIN
        const QString embedded=QCoreApplication::applicationDirPath()+"/runtime/backend/studio-backend/studio-backend.exe";
#else
        const QString embedded=QCoreApplication::applicationDirPath()+"/runtime/backend/studio-backend/studio-backend";
#endif
        if (QFileInfo::exists(embedded)) { program=embedded; arguments=QStringList{QStringLiteral("run")}; }
    }
    if (!QFileInfo::exists(program)) {
        QMessageBox::warning(this,tr("Python runtime missing"),tr("Build the private runtime with the studio-python-runtime CMake target, or set SU2_STUDIO_PYTHON."));
        return;
    }
    process_.setWorkingDirectory(arguments.size()==1 ? QCoreApplication::applicationDirPath() : sourceRoot());
    process_.start(program,arguments);
    if(!process_.waitForStarted(5000)){log_->appendPlainText(process_.errorString());return;}
    process_.write(requestBytes);process_.closeWriteChannel();
    meshAction_->setEnabled(false);solveAction_->setEnabled(false);optimizeAction_->setEnabled(false);stopAction_->setEnabled(true);
    pauseAction_->setEnabled(mode==QStringLiteral("solve"));stopAfterSaveAction_->setEnabled(mode==QStringLiteral("solve"));
    summary_->setText(tr("Running"));
}
void MainWindow::finish(int code,QProcess::ExitStatus status) {
    const QByteArray bytes=process_.readAllStandardOutput();QJsonParseError parseError;const auto document=QJsonDocument::fromJson(bytes,&parseError);
    if(parseError.error==QJsonParseError::NoError && document.isObject()) {
        const auto response=document.object();
        if(response.value("ok").toBool()) {
            const QString resultDirectory=response.value("output_dir").toString();
            log_->appendPlainText(tr("Completed: %1").arg(resultDirectory));
            if (currentMode_==QStringLiteral("optimize")) {
                const QJsonObject final=response.value(QStringLiteral("study")).toObject().value(QStringLiteral("final")).toObject();
                log_->appendPlainText(tr("Accepted optimization steps: %1").arg(final.value(QStringLiteral("accepted_steps")).toInt()));
                const QString foil=final.value(QStringLiteral("airfoil_dat")).toString();
                if (!foil.isEmpty()) {QString error;if(view_->loadDat(foil,&error))tabs_->setCurrentIndex(0);}
            } else openCase(resultDirectory);
        }
        else log_->appendPlainText(response.value("error").toObject().value("message").toString());
    } else log_->appendPlainText(tr("Backend returned an invalid response."));
    meshAction_->setEnabled(true);solveAction_->setEnabled(true);optimizeAction_->setEnabled(true);stopAction_->setEnabled(false);
    pauseAction_->setEnabled(false);stopAfterSaveAction_->setEnabled(false);solverPaused_=false;
    summary_->setText(code==0 && status==QProcess::NormalExit?tr("Complete"):tr("Failed"));
}
void MainWindow::closeEvent(QCloseEvent *event) {
    if(process_.state()!=QProcess::NotRunning) {QMessageBox::warning(this,tr("Task running"),tr("Stop the active task before closing."));event->ignore();return;}
    QSettings settings;settings.setValue("geometry",saveGeometry());settings.setValue("state",saveState());settings.setValue("directory",directory_->text());settings.setValue("su2Executable",su2Path_->text());settings.setValue("gmshPythonPath",gmshPath_->text());QMainWindow::closeEvent(event);
}

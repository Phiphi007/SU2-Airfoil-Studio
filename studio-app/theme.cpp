#include "theme.h"
#include <QApplication>
#include <QColor>
#include <QPalette>
#include <QStyleFactory>

void StudioTheme::apply(const QString &name) {
    const bool dark = name == QStringLiteral("dark");
    QApplication::setStyle(QStyleFactory::create("Fusion"));
    QPalette palette;
    palette.setColor(QPalette::Window, QColor(dark ? "#202b36" : "#f4f6f8"));
    palette.setColor(QPalette::WindowText, QColor(dark ? "#e7edf3" : "#182430"));
    palette.setColor(QPalette::Base, QColor(dark ? "#17212b" : "#ffffff"));
    palette.setColor(QPalette::AlternateBase, QColor(dark ? "#24313e" : "#edf1f4"));
    palette.setColor(QPalette::Text, QColor(dark ? "#e7edf3" : "#182430"));
    palette.setColor(QPalette::Button, QColor(dark ? "#2b3947" : "#e6ebef"));
    palette.setColor(QPalette::ButtonText, QColor(dark ? "#e7edf3" : "#182430"));
    palette.setColor(QPalette::Highlight, QColor(dark ? "#318caf" : "#167ca6"));
    palette.setColor(QPalette::HighlightedText, QColor("#ffffff"));
    palette.setColor(QPalette::PlaceholderText, QColor(dark ? "#aab8c6" : "#657382"));
    palette.setColor(QPalette::ToolTipBase, QColor(dark ? "#263645" : "#ffffff"));
    palette.setColor(QPalette::ToolTipText, QColor(dark ? "#e7edf3" : "#182430"));
    qApp->setPalette(palette);
    qApp->setStyleSheet(QStringLiteral("QDockWidget::title { background: %1; padding: 7px; }"
                                       "QToolBar { spacing: 8px; padding: 5px; }"
                                       "QStatusBar { border-top: 1px solid %2; }"
                                       "QTreeWidget { border: 0; }")
                            .arg(dark ? "#263645" : "#e6ebef", dark ? "#394b5b" : "#ccd5dc"));
}

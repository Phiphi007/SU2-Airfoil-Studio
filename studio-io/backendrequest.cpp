#include "backendrequest.h"
#include <QJsonDocument>
#include <QJsonObject>
QByteArray encodeRequest(const RunSettings &s) {
    const QJsonObject parameters{{"surface_points",s.surfacePoints},{"global_refinement",s.refinement},
        {"mach",s.mach},{"aoa",s.angleOfAttack},{"reynolds",s.reynolds},{"iterations",s.iterations},
        {"solver",s.solver}};
    const QJsonObject request{{"api_version",1},{"mode",s.mode},
        {"airfoil",s.airfoil.isEmpty() ? QStringLiteral("builtin://naca0012") : s.airfoil},
        {"output_dir",s.outputDirectory},{"parameters",parameters}};
    return QJsonDocument(request).toJson(QJsonDocument::Compact);
}

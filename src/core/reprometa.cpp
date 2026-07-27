#include "core/reprometa.hpp"

#include <QJsonObject>
#include <QString>

namespace ReproMeta
{

QJsonObject planStamp()
{
    return QJsonObject{
        {QStringLiteral("schema"), 1},
        {QStringLiteral("seed"), kIcaRandomState},
        {QStringLiteral("ica_random_state"), kIcaRandomState},
        {QStringLiteral("note"),
         QStringLiteral(
             "Stochastic steps use ica_random_state. Library versions are recorded in "
             "run.json when the plan is executed.")},
    };
}

} // namespace ReproMeta

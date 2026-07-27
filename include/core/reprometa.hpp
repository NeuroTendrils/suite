#pragma once

#include <QJsonObject>

// Suite-side reproducibility stamps for NeuroFlow plans / runs.
// Keep ica_random_state in sync with workers/neuroflow/neuroflow/repro.py.
namespace ReproMeta
{

inline constexpr int kIcaRandomState = 42;

// Base block written into plan JSON on save (library versions filled at run time).
[[nodiscard]] QJsonObject planStamp();

} // namespace ReproMeta

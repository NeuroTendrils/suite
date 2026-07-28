cmake_minimum_required(VERSION 3.21)

project(NeuroTendrils
    VERSION 0.0.1
    DESCRIPTION "NeuroTendrils Suite"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets)

qt_standard_project_setup()

qt_add_executable(neurotendrils
    src/main.cpp
    src/mainwindow.cpp
    include/mainwindow.hpp
    src/core/theme.cpp
    include/core/theme.hpp
    src/core/projectdir.cpp
    include/core/projectdir.hpp
    src/core/pythonruntime.cpp
    include/core/pythonruntime.hpp
    src/core/ipcredact.cpp
    include/core/ipcredact.hpp
    src/core/workerclient.cpp
    include/core/workerclient.hpp
    src/core/datasetimport.cpp
    include/core/datasetimport.hpp
    src/core/studiodataset.cpp
    include/core/studiodataset.hpp
    src/core/stepcatalog.cpp
    include/core/stepcatalog.hpp
    src/core/plangenerator.cpp
    include/core/plangenerator.hpp
    src/core/planio.cpp
    include/core/planio.hpp
    src/core/runio.cpp
    include/core/runio.hpp
    src/core/reprometa.cpp
    include/core/reprometa.hpp
    src/settingsdialog.cpp
    include/settingsdialog.hpp
    src/widgets/icons.cpp
    include/widgets/icons.hpp
    src/widgets/pageheader.cpp
    include/widgets/pageheader.hpp
    src/widgets/themepreviewcard.cpp
    include/widgets/themepreviewcard.hpp
    src/widgets/skeletonloader.cpp
    include/widgets/skeletonloader.hpp
    src/modules/neuroflow/neuroflowpage.cpp
    include/modules/neuroflow/neuroflowpage.hpp
    src/modules/neuroflow/stepeditdialog.cpp
    include/modules/neuroflow/stepeditdialog.hpp
    src/modules/neurostudio/neurostudiopage.cpp
    include/modules/neurostudio/neurostudiopage.hpp
    src/modules/neurolearn/neurolearnpage.cpp
    include/modules/neurolearn/neurolearnpage.hpp
    src/modules/hub/hubpage.cpp
    include/modules/hub/hubpage.hpp
)

qt_add_resources(neurotendrils "fonts"
    PREFIX "/fonts"
    BASE resources/fonts
    FILES
        resources/fonts/Inter-Regular.ttf
        resources/fonts/Inter-Medium.ttf
        resources/fonts/Inter-SemiBold.ttf
        resources/fonts/Inter-Bold.ttf
)

target_include_directories(neurotendrils PRIVATE include)

target_link_libraries(neurotendrils PRIVATE Qt6::Widgets)

set_target_properties(neurotendrils PROPERTIES
    WIN32_EXECUTABLE ON
    MACOSX_BUNDLE ON
)

# Local IPC round-trip tool (no CI wiring yet). Run from the suite repo root:
#   cmake --build build --target neurotendrils_ipc_roundtrip
#   ./build/neurotendrils_ipc_roundtrip
qt_add_executable(neurotendrils_ipc_roundtrip
    tests/worker_ipc_roundtrip.cpp
    src/core/projectdir.cpp
    include/core/projectdir.hpp
    src/core/pythonruntime.cpp
    include/core/pythonruntime.hpp
    src/core/ipcredact.cpp
    include/core/ipcredact.hpp
    src/core/workerclient.cpp
    include/core/workerclient.hpp
)

target_include_directories(neurotendrils_ipc_roundtrip PRIVATE include)
target_link_libraries(neurotendrils_ipc_roundtrip PRIVATE Qt6::Widgets)

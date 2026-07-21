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
    src/modules/neuroflow/neuroflowpage.cpp
    include/modules/neuroflow/neuroflowpage.hpp
    src/modules/neurostudio/neurostudiopage.cpp
    include/modules/neurostudio/neurostudiopage.hpp
    src/modules/neurolearn/neurolearnpage.cpp
    include/modules/neurolearn/neurolearnpage.hpp
    src/modules/hub/hubpage.cpp
    include/modules/hub/hubpage.hpp
)

target_include_directories(neurotendrils PRIVATE include)

target_link_libraries(neurotendrils PRIVATE Qt6::Widgets)

set_target_properties(neurotendrils PROPERTIES
    WIN32_EXECUTABLE ON
    MACOSX_BUNDLE ON
)

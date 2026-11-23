cmake_minimum_required(VERSION 3.16)
project(SU2AirfoilStudio VERSION 2.0.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.8 REQUIRED COMPONENTS Widgets LinguistTools)
add_subdirectory(studio-lib)
add_subdirectory(studio-io)
add_subdirectory(studio-app)
include(CTest)
if(BUILD_TESTING)
  add_executable(studio-fieldview-test tests/cpp/test_fieldview.cpp)
  target_link_libraries(studio-fieldview-test PRIVATE studio_geometry Qt6::Widgets)
  add_test(NAME studio-fieldview-interaction COMMAND studio-fieldview-test)
  set_tests_properties(studio-fieldview-interaction PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
  add_executable(studio-airfoilview-test tests/cpp/test_airfoilview.cpp)
  target_link_libraries(studio-airfoilview-test PRIVATE studio_geometry Qt6::Widgets)
  add_test(NAME studio-naca4-geometry COMMAND studio-airfoilview-test)
  set_tests_properties(studio-naca4-geometry PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
  option(STUDIO_ENABLE_GUI_INTEGRATION "Run GUI actions against the frozen backend" OFF)
  if(STUDIO_ENABLE_GUI_INTEGRATION)
    set(STUDIO_GUI_TEST_PYTHON "" CACHE FILEPATH "Prepared private Python interpreter for the GUI integration test")
    set(STUDIO_GUI_TEST_SU2 "" CACHE FILEPATH "Built SU2_CFD for the GUI integration test")
    if(NOT EXISTS "${STUDIO_GUI_TEST_PYTHON}")
      message(FATAL_ERROR "Set STUDIO_GUI_TEST_PYTHON to a prepared private runtime")
    endif()
    if(NOT EXISTS "${STUDIO_GUI_TEST_SU2}")
      message(FATAL_ERROR "Set STUDIO_GUI_TEST_SU2 to a built SU2_CFD executable")
    endif()
    add_executable(studio-gui-workflow-test tests/cpp/test_gui_workflow.cpp
      studio-app/mainwindow.cpp studio-app/mainwindow.h studio-app/theme.cpp studio-app/theme.h
      studio-app/fonts.qrc)
    target_link_libraries(studio-gui-workflow-test PRIVATE studio_geometry studio_io Qt6::Widgets)
    target_include_directories(studio-gui-workflow-test PRIVATE "${PROJECT_SOURCE_DIR}/studio-app")
    target_compile_definitions(studio-gui-workflow-test PRIVATE STUDIO_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
    add_test(NAME studio-gui-mesh-workflow COMMAND studio-gui-workflow-test)
    set_tests_properties(studio-gui-mesh-workflow PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;MPLBACKEND=Agg;SU2_STUDIO_PYTHON=${STUDIO_GUI_TEST_PYTHON};SU2AUTOFOIL_SU2_EXECUTABLE=${STUDIO_GUI_TEST_SU2}" TIMEOUT 120)
  endif()
endif()

# Build this target explicitly to provision an isolated backend next to the executable.
# Configure STUDIO_BOOTSTRAP_PYTHON to use a specific interpreter such as conda science.
set(STUDIO_BOOTSTRAP_PYTHON "" CACHE FILEPATH "Python interpreter used to create the private runtime")
if(NOT STUDIO_BOOTSTRAP_PYTHON)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  set(STUDIO_BOOTSTRAP_PYTHON "${Python3_EXECUTABLE}")
endif()
find_path(STUDIO_EIGEN_INCLUDE_DIR Eigen/Core PATH_SUFFIXES eigen3)
set(STUDIO_SU2_BIN "${PROJECT_SOURCE_DIR}/build/su2-native" CACHE PATH "SU2 Meson build directory containing CFD, adjoint, DOT and deformation executables")
set(STUDIO_SU2_BUILD_ARGS "")
if(STUDIO_EIGEN_INCLUDE_DIR)
  list(APPEND STUDIO_SU2_BUILD_ARGS --eigen-include "${STUDIO_EIGEN_INCLUDE_DIR}")
endif()
add_custom_target(studio-su2
  COMMAND "${STUDIO_BOOTSTRAP_PYTHON}" "${PROJECT_SOURCE_DIR}/scripts/build_su2.py"
    --build-dir "${STUDIO_SU2_BIN}" ${STUDIO_SU2_BUILD_ARGS}
  USES_TERMINAL
  COMMENT "Building pinned SU2 direct and adjoint solver executables")
add_custom_target(studio-python-runtime
  COMMAND "${STUDIO_BOOTSTRAP_PYTHON}" "${PROJECT_SOURCE_DIR}/scripts/build_python_runtime.py"
    --bootstrap-python "${STUDIO_BOOTSTRAP_PYTHON}"
    --destination "$<TARGET_FILE_DIR:su2-airfoil-studio>/runtime/python"
  DEPENDS su2-airfoil-studio
  USES_TERMINAL
  COMMENT "Provisioning the isolated Python backend runtime")
add_custom_target(studio-backend-bundle
  COMMAND "$<TARGET_FILE_DIR:su2-airfoil-studio>/runtime/python/$<IF:$<PLATFORM_ID:Windows>,Scripts/python.exe,bin/python>"
    "${PROJECT_SOURCE_DIR}/scripts/build_embedded_backend.py"
    --output "$<TARGET_FILE_DIR:su2-airfoil-studio>/runtime/backend"
  DEPENDS studio-python-runtime
  USES_TERMINAL
  COMMENT "Freezing the Python backend for distribution")
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(STUDIO_LINUXDEPLOY "" CACHE FILEPATH "Path to linuxdeploy AppImage")
  set(STUDIO_LINUXDEPLOY_QT_PLUGIN "" CACHE FILEPATH "Path to linuxdeploy Qt plugin AppImage")
  set(STUDIO_APPIMAGE_RUNTIME "" CACHE FILEPATH "Path to AppImage type-2 runtime")
  set(STUDIO_QT_OFFSCREEN_PLUGIN "" CACHE FILEPATH "Qt offscreen platform plugin for smoke tests")
  if(STUDIO_LINUXDEPLOY AND STUDIO_LINUXDEPLOY_QT_PLUGIN)
    get_target_property(STUDIO_QT_QMAKE Qt6::qmake IMPORTED_LOCATION)
    add_custom_target(studio-appimage
      COMMAND "${STUDIO_BOOTSTRAP_PYTHON}" "${PROJECT_SOURCE_DIR}/scripts/build_appimage.py"
        --build-dir "${CMAKE_BINARY_DIR}" --linuxdeploy "${STUDIO_LINUXDEPLOY}"
        --qt-plugin "${STUDIO_LINUXDEPLOY_QT_PLUGIN}" --qmake "${STUDIO_QT_QMAKE}"
        --su2-bin "${STUDIO_SU2_BIN}"
        $<$<BOOL:${STUDIO_APPIMAGE_RUNTIME}>:--runtime-file> $<$<BOOL:${STUDIO_APPIMAGE_RUNTIME}>:${STUDIO_APPIMAGE_RUNTIME}>
        $<$<BOOL:${STUDIO_QT_OFFSCREEN_PLUGIN}>:--offscreen-plugin> $<$<BOOL:${STUDIO_QT_OFFSCREEN_PLUGIN}>:${STUDIO_QT_OFFSCREEN_PLUGIN}>
      DEPENDS studio-backend-bundle studio-su2
      USES_TERMINAL
      COMMENT "Building SU2 Airfoil Studio AppImage")
  endif()
endif()
if(WIN32)
  get_target_property(STUDIO_QT_QMAKE Qt6::qmake IMPORTED_LOCATION)
  get_filename_component(STUDIO_QT_BIN_DIR "${STUDIO_QT_QMAKE}" DIRECTORY)
  add_custom_target(studio-windows-bundle
    COMMAND "${STUDIO_BOOTSTRAP_PYTHON}" "${PROJECT_SOURCE_DIR}/scripts/build_windows_bundle.py"
      --exe "$<TARGET_FILE:su2-airfoil-studio>"
      --backend "$<TARGET_FILE_DIR:su2-airfoil-studio>/runtime/backend/studio-backend"
      --translation "$<TARGET_FILE_DIR:su2-airfoil-studio>/studio_zh_CN.qm"
      --su2-bin "${STUDIO_SU2_BIN}"
      --windeployqt "${STUDIO_QT_BIN_DIR}/windeployqt.exe"
      --output "${CMAKE_BINARY_DIR}/release/SU2-Airfoil-Studio"
    DEPENDS studio-backend-bundle
    USES_TERMINAL
    COMMENT "Staging the double-clickable Windows desktop folder")
endif()

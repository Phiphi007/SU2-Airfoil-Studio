add_library(studio_geometry STATIC airfoilview.cpp airfoilview.h fieldview.cpp fieldview.h historyview.cpp historyview.h)
target_link_libraries(studio_geometry PUBLIC Qt6::Widgets)
target_include_directories(studio_geometry PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

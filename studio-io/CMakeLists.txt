add_library(studio_io STATIC backendrequest.cpp backendrequest.h)
target_link_libraries(studio_io PUBLIC Qt6::Widgets)
target_include_directories(studio_io PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

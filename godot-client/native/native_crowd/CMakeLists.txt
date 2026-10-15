cmake_minimum_required(VERSION 3.17)

project(native_crowd VERSION 0.1 LANGUAGES CXX)

include(FetchContent)

# godot-cpp 10.0.0-stable. This release can generate bindings for Godot 4.7.
# A commit rather than a moving branch keeps benchmark builds reproducible.
set(GODOT_CPP_REVISION
    "507ed9d840c01a3c5b2a39af8bb4000bfac30bf5"
    CACHE STRING "Pinned godot-cpp revision")
set(GODOTCPP_API_VERSION "4.7" CACHE STRING "" FORCE)
set(GODOTCPP_BUILD_PROFILE
    "${CMAKE_CURRENT_SOURCE_DIR}/build_profile.json"
    CACHE FILEPATH "" FORCE)
set(GODOTCPP_SYSTEM_HEADERS ON CACHE BOOL "" FORCE)
set(GODOTCPP_USE_HOT_RELOAD OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
    godot_cpp
    GIT_REPOSITORY https://github.com/godotengine/godot-cpp.git
    GIT_TAG ${GODOT_CPP_REVISION}
    GIT_SHALLOW FALSE
    SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/.deps/godot-cpp"
)
FetchContent_MakeAvailable(godot_cpp)

add_library(native_crowd SHARED
    src/native_crowd_reducer.cpp
    src/native_crowd_reducer.h
    src/native_spell_flight_geometry.cpp
    src/native_spell_flight_geometry.h
    src/native_cape_constraint_kernel.cpp
    src/native_cape_constraint_kernel.h
    src/native_world_effect_geometry.cpp
    src/native_world_effect_geometry.h
    src/register_types.cpp
    src/register_types.h
)
target_link_libraries(native_crowd PRIVATE godot-cpp)
target_compile_features(native_crowd PRIVATE cxx_std_17)
if(MINGW)
    # Keep the benchmark artifact self-contained. Do not require a machine-wide
    # MinGW runtime installation or mutate the process PATH to find its DLLs.
    target_link_options(native_crowd PRIVATE -static-libgcc -static-libstdc++)
endif()

get_target_property(GODOTCPP_SUFFIX godot::cpp GODOTCPP_SUFFIX)
get_target_property(GODOTCPP_PLATFORM godot::cpp GODOTCPP_PLATFORM)

set_target_properties(native_crowd PROPERTIES
    PREFIX ""
    OUTPUT_NAME "native_crowd${GODOTCPP_SUFFIX}"
    RUNTIME_OUTPUT_DIRECTORY
        "${CMAKE_CURRENT_SOURCE_DIR}/../../bin/${GODOTCPP_PLATFORM}"
    LIBRARY_OUTPUT_DIRECTORY
        "${CMAKE_CURRENT_SOURCE_DIR}/../../bin/${GODOTCPP_PLATFORM}"
)

# Godot sees the descriptor only after a successful native build, so a normal
# source checkout never reports a missing extension library during import.
file(MAKE_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../../bin")
add_custom_command(TARGET native_crowd POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/native_crowd.gdextension.in"
        "${CMAKE_CURRENT_SOURCE_DIR}/../../bin/native_crowd.gdextension"
)

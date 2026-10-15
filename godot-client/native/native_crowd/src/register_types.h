#pragma once

#include <godot_cpp/core/class_db.hpp>

void initialize_native_crowd_module(
        godot::ModuleInitializationLevel initialization_level);
void uninitialize_native_crowd_module(
        godot::ModuleInitializationLevel initialization_level);


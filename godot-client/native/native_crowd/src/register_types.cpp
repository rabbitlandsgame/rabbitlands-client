#include "register_types.h"

#include "native_crowd_reducer.h"
#include "native_spell_flight_geometry.h"
#include "native_cape_constraint_kernel.h"
#include "native_world_effect_geometry.h"

#include <gdextension_interface.h>
#include <godot_cpp/core/defs.hpp>
#include <godot_cpp/godot.hpp>

using namespace godot;

void initialize_native_crowd_module(
        ModuleInitializationLevel initialization_level) {
    if (initialization_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
        return;
    }
    ClassDB::register_class<NativeCrowdReducer>();
    ClassDB::register_class<NativeCrowdStore>();
    ClassDB::register_class<NativeSpellFlightGeometry>();
    ClassDB::register_class<NativeCapeConstraintKernel>();
    ClassDB::register_class<NativeWorldEffectGeometry>();
}

void uninitialize_native_crowd_module(
        ModuleInitializationLevel initialization_level) {
    if (initialization_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
        return;
    }
}

extern "C" {
GDExtensionBool GDE_EXPORT native_crowd_library_init(
        GDExtensionInterfaceGetProcAddress get_proc_address,
        const GDExtensionClassLibraryPtr library,
        GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject init_object(
            get_proc_address, library, initialization);
    init_object.register_initializer(initialize_native_crowd_module);
    init_object.register_terminator(uninitialize_native_crowd_module);
    init_object.set_minimum_library_initialization_level(
            MODULE_INITIALIZATION_LEVEL_SCENE);
    return init_object.init();
}
}

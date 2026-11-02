#include <godot_cpp/godot.hpp>
#include <godot_cpp/core/class_db.hpp>
#include "../client_runtime/src/mounted_cape_body_surface.h"
#include "../client_runtime/src/mounted_cape_projector.h"

using namespace godot;
extern void rl_cape_shutdown_contact_workers();

static void initialize_browser_cape(ModuleInitializationLevel level) {
    if (level != MODULE_INITIALIZATION_LEVEL_SCENE) return;
    ClassDB::register_class<RabbitLandsCapeBodySurface>();
    ClassDB::register_class<RabbitLandsCapeProjector>();
}
static void terminate_browser_cape(ModuleInitializationLevel level) {
    if (level == MODULE_INITIALIZATION_LEVEL_SCENE) rl_cape_shutdown_contact_workers();
}
// The editor counterpart uses the existing desktop adapter's entry symbol;
// the browser library registers only the two arithmetic classes above.
extern "C" GDExtensionBool GDE_EXPORT rl_client_runtime_library_init(
    GDExtensionInterfaceGetProcAddress address, GDExtensionClassLibraryPtr library,
    GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject object(address, library, initialization);
    object.register_initializer(initialize_browser_cape);
    object.register_terminator(terminate_browser_cape);
    object.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return object.init();
}

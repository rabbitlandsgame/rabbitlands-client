/* Native bundle entry point. Keep the legacy loose-file layout beneath Resources
 * and set its working directory before Godot or any autoload reads an asset.
 * No shell parsing, environment-dependent paths, or install-directory writes. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char executable[PATH_MAX], resolved[PATH_MAX];
    uint32_t size = sizeof(executable);
    if (_NSGetExecutablePath(executable, &size) || !realpath(executable, resolved)) {
        perror("Rabbit Lands executable path"); return 1;
    }
    char *name = strrchr(resolved, '/');
    if (!name) return 1;
    *name = '\0'; /* Contents/MacOS */
    name = strrchr(resolved, '/');
    if (!name) return 1;
    *name = '\0'; /* Contents */
    char game[PATH_MAX], helper[PATH_MAX];
    if (snprintf(game, sizeof(game), "%s/Resources/game/app", resolved) >= sizeof(game) ||
        snprintf(helper, sizeof(helper), "%s/Helpers/RabbitLands", resolved) >= sizeof(helper)) return 1;
    if (chdir(game)) { perror("Rabbit Lands game files"); return 1; }
    char **args = calloc((size_t)argc + 1, sizeof(char *));
    if (!args) return 1;
    args[0] = helper;
    for (int i = 1; i < argc; i++) args[i] = argv[i];
    execv(helper, args);
    perror("Rabbit Lands game launch");
    free(args); return 1;
}

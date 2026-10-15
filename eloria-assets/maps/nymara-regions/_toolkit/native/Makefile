# Offline preview rasteriser. Not part of the runtime package - it exists only
# so a region can be looked at while it is being authored.
#
# The output keeps the .so name on every platform because render.py loads it by
# path through ctypes, which does not care about the extension. On Windows
# (MSYS2/mingw-w64) link the runtime statically so plain CPython can load it
# without mingw's DLLs on PATH.
CFLAGS ?= -O3 -ffast-math -shared

UNAME_S := $(shell uname -s)
ifneq (,$(findstring MINGW,$(UNAME_S)))
  PLATFORM_FLAGS = -static-libgcc -static
else
ifneq (,$(findstring MSYS,$(UNAME_S)))
  PLATFORM_FLAGS = -static-libgcc -static
else
  PLATFORM_FLAGS = -fPIC
endif
endif

libraster.so: raster.c
	$(CC) $(CFLAGS) $(PLATFORM_FLAGS) -o $@ $< -lm

clean:
	rm -f libraster.so

.PHONY: clean

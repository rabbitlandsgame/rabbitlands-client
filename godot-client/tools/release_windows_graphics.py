"""Identify system WARP in the same DXGI enumeration order as pinned Godot.

No driver is installed, copied, or shipped. EnumWarpAdapter supplies the
independent identity; a display name alone is never a software-adapter proof.
Interface slots/layouts follow Windows SDK 10.0.26100 dxgi.h/dxgi1_6.h.
Godot ed1daf0bf create_adapter uses HIGH_PERFORMANCE preference order.
"""
from __future__ import annotations

import ctypes
import re
import sys
import uuid

POLICY = "rl-windows-warp-selection-v1"
SOFTWARE = 2
NOT_FOUND = 0x887A0002
FACTORY6 = "c1b6694f-ff09-44a9-b03c-77900a0a1d17"
ADAPTER1 = "29038f61-3839-4626-91fd-086879011a05"
DESCRIPTOR_FIELDS = frozenset(("name", "vendor_id", "device_id", "subsystem_id", "revision", "luid", "flags",
                              "dedicated_video_memory", "dedicated_system_memory", "shared_system_memory"))


def enumerate_adapters():
    """Read the installed system DXGI factory; release every COM reference."""
    if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise ValueError("WARP selection requires native 64-bit Windows")
    from ctypes import POINTER, Structure, byref, c_int32, c_uint32, c_uint64, c_void_p

    class Guid(Structure):
        _fields_ = [("bytes", ctypes.c_ubyte * 16)]

    class Luid(Structure):
        _fields_ = [("low", c_uint32), ("high", c_int32)]

    class Description(Structure):
        _fields_ = [("name", ctypes.c_wchar * 128), ("vendor", c_uint32),
                    ("device", c_uint32), ("subsystem", c_uint32), ("revision", c_uint32),
                    ("video", c_uint64), ("system", c_uint64), ("shared", c_uint64),
                    ("luid", Luid), ("flags", c_uint32)]

    if ctypes.sizeof(Description) != 312:
        raise ValueError("Unexpected Windows DXGI adapter descriptor ABI")
    iid_factory = Guid.from_buffer_copy(uuid.UUID(FACTORY6).bytes_le)
    iid_adapter = Guid.from_buffer_copy(uuid.UUID(ADAPTER1).bytes_le)
    # LOAD_LIBRARY_SEARCH_SYSTEM32 prevents a checkout/PATH DLL substitution.
    dxgi = ctypes.WinDLL("dxgi.dll", winmode=0x800)
    create = dxgi.CreateDXGIFactory2
    create.argtypes = [c_uint32, POINTER(Guid), POINTER(c_void_p)]
    create.restype = c_int32

    def checked(result, operation):
        if result < 0:
            raise ValueError(f"{operation} failed: HRESULT 0x{result & 0xffffffff:08x}")

    def invoke(pointer, slot, result, types, *arguments):
        table = ctypes.cast(pointer, POINTER(POINTER(c_void_p))).contents
        return ctypes.WINFUNCTYPE(result, c_void_p, *types)(table[slot])(pointer, *arguments)

    def release(pointer):
        if pointer:
            invoke(pointer, 2, c_uint32, [])

    def describe(pointer):
        value = Description()
        checked(invoke(pointer, 10, c_int32, [POINTER(Description)], byref(value)), "GetDesc1")
        return {"name": value.name, "vendor_id": value.vendor, "device_id": value.device,
                "subsystem_id": value.subsystem, "revision": value.revision,
                "luid": f"{value.luid.high & 0xffffffff:08x}:{value.luid.low:08x}",
                "flags": value.flags, "dedicated_video_memory": value.video,
                "dedicated_system_memory": value.system, "shared_system_memory": value.shared}

    factory, warp = c_void_p(), c_void_p()
    try:
        checked(create(0, byref(iid_factory), byref(factory)), "CreateDXGIFactory2/IDXGIFactory6")
        checked(invoke(factory, 27, c_int32, [POINTER(Guid), POINTER(c_void_p)],
                       byref(iid_adapter), byref(warp)), "EnumWarpAdapter")
        warp_description = describe(warp)
        adapters = []
        for index in range(32):
            adapter = c_void_p()
            try:
                result = invoke(factory, 29, c_int32,
                    [c_uint32, c_uint32, POINTER(Guid), POINTER(c_void_p)],
                    index, 2, byref(iid_adapter), byref(adapter))
                if result & 0xffffffff == NOT_FOUND:
                    break
                checked(result, "EnumAdapterByGpuPreference(HIGH_PERFORMANCE)")
                adapters.append(dict(index=index, **describe(adapter)))
            finally:
                release(adapter)
        else:
            raise ValueError("DXGI adapter enumeration exceeded its 32-device bound")
        return {"schema": 1, "policy": POLICY,
                "system_dxgi": "System32/dxgi.dll", "factory": "IDXGIFactory6",
                "enumeration": "EnumAdapterByGpuPreference(HIGH_PERFORMANCE)",
                "warp": warp_description, "adapters": adapters}
    finally:
        release(warp)
        release(factory)


def select_warp(inventory, requested_index=None):
    """Match independent WARP LUID/descriptor/flag, never a guessed index."""
    if (not isinstance(inventory, dict) or type(inventory.get("schema")) is not int or inventory["schema"] != 1
            or inventory.get("policy") != POLICY or inventory.get("factory") != "IDXGIFactory6"
            or inventory.get("system_dxgi") != "System32/dxgi.dll"
            or inventory.get("enumeration") != "EnumAdapterByGpuPreference(HIGH_PERFORMANCE)"):
        raise ValueError("Unsupported DXGI enumeration evidence")
    warp, adapters = inventory.get("warp"), inventory.get("adapters")

    def descriptor(value):
        return (isinstance(value, dict) and set(value) == DESCRIPTOR_FIELDS
                and isinstance(value["name"], str) and bool(value["name"].strip())
                and isinstance(value["luid"], str) and bool(re.fullmatch(r"[0-9a-f]{8}:[0-9a-f]{8}", value["luid"]))
                and all(type(value[key]) is int and 0 <= value[key] < (1 << (64 if "memory" in key else 32))
                        for key in DESCRIPTOR_FIELDS - {"name", "luid"}))

    if not descriptor(warp) or not warp["flags"] & SOFTWARE or not isinstance(adapters, list) or not 0 < len(adapters) <= 32:
        raise ValueError("Independent EnumWarpAdapter lacks software/LUID evidence")
    luids = set()
    for index, row in enumerate(adapters):
        if (not isinstance(row, dict) or type(row.get("index")) is not int or row["index"] != index
                or not descriptor({key: value for key, value in row.items() if key != "index"})
                or row["luid"] in luids):
            raise ValueError("DXGI preferred-order adapter inventory is malformed or ambiguous")
        luids.add(row["luid"])
    matches = [row for row in adapters if {key: value for key, value in row.items() if key != "index"} == warp]
    if len(matches) != 1:
        raise ValueError("Independent WARP identity is not unique in Godot's preferred adapter order")
    selected = matches[0]
    if requested_index is not None and (type(requested_index) is not int or requested_index != selected["index"]):
        raise ValueError("Requested GPU index does not identify the actual system WARP adapter")
    return dict(inventory, selected_index=selected["index"], selected_adapter=dict(selected))


def identify_warp(gpu_index=None):
    return select_warp(enumerate_adapters(), gpu_index)

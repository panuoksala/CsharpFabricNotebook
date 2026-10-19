"""
Locates and loads the .NET CoreCLR runtime that is bundled inside this package,
and loads the ScriptHost assembly that exposes the Roslyn C# scripting engine.

Nothing here requires the .NET SDK (or even the .NET runtime) to be installed
on the host machine: the `runtime/<rid>/` folders contain a self-contained
publish of ScriptHost, including the CoreCLR runtime files themselves.
"""
from __future__ import annotations

import os
import sys
import threading

_lock = threading.Lock()
_loaded = False


def _runtime_identifier() -> str:
    if sys.platform.startswith("win"):
        return "win-x64"
    if sys.platform.startswith("linux"):
        return "linux-x64"
    raise RuntimeError(f"Unsupported platform for fabric_csharp: {sys.platform}")


def _runtime_dir() -> str:
    rid = _runtime_identifier()
    path = os.path.join(os.path.dirname(__file__), "runtime", rid)
    if not os.path.isdir(path):
        raise RuntimeError(
            f"Bundled .NET runtime for '{rid}' not found at {path}. "
            "The package was not built with the required runtime assets "
            "(see build.ps1 / README)."
        )
    return path


def _ensure_executable_bits(dotnet_root: str) -> None:
    """Wheels built/extracted on non-POSIX tooling (e.g. a Windows build
    machine) can lose the executable bit on native .so files. Re-assert it
    before asking the loader to dlopen anything under dotnet_root."""
    for dirpath, _dirnames, filenames in os.walk(dotnet_root):
        for name in filenames:
            if name.endswith(".so") or ".so." in name:
                full_path = os.path.join(dirpath, name)
                try:
                    st = os.stat(full_path)
                    os.chmod(full_path, st.st_mode | 0o111)
                except OSError:
                    pass


def ensure_clr_loaded() -> None:
    """Idempotently boot CoreCLR in-process and load ScriptHost.dll.

    Layout produced by build.ps1 for each runtime identifier (rid):
        runtime/<rid>/app/            ScriptHost.dll, its Roslyn dependencies,
                                       ScriptHost.deps.json/.runtimeconfig.json
        runtime/<rid>/dotnetroot/
            shared/Microsoft.NETCore.App/<version>/   bundled CoreCLR runtime

    We point clr_loader's coreclr backend at the app's runtimeconfig.json and
    at our bundled "dotnetroot" (via the dotnet_root parameter) so the CoreCLR
    framework is resolved entirely from files shipped inside this package -
    no system-wide .NET install is required.
    """
    global _loaded
    if _loaded:
        return

    with _lock:
        if _loaded:
            return

        runtime_dir = _runtime_dir()
        app_dir = os.path.join(runtime_dir, "app")
        dotnet_root = os.path.join(runtime_dir, "dotnetroot")
        runtimeconfig = os.path.join(app_dir, "ScriptHost.runtimeconfig.json")

        if not os.path.isfile(runtimeconfig):
            raise RuntimeError(f"Missing runtimeconfig.json at {runtimeconfig}")
        if not os.path.isdir(dotnet_root):
            raise RuntimeError(f"Missing bundled .NET runtime at {dotnet_root}")

        if not sys.platform.startswith("win"):
            _ensure_executable_bits(dotnet_root)

        # Keep the bundled runtime self-sufficient / small (no ICU dependency).
        os.environ.setdefault("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1")

        import pythonnet

        pythonnet.load("coreclr", runtime_config=runtimeconfig, dotnet_root=dotnet_root)

        import clr  # noqa: F401  (import registers the CLR import hook)

        clr.AddReference(os.path.join(app_dir, "ScriptHost.dll"))

        _loaded = True

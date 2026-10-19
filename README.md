# CsharpFabricNotebook

Run C# directly in Microsoft Fabric notebook cells using a custom IPython
extension, pythonnet, and Roslyn scripting. The Python wheel bundles a .NET 8
runtime, so notebook users do not need a separate .NET SDK or runtime installation.

**Experimental:** this is not an official Microsoft Fabric language or kernel.
Validate the bundled runtime in your own Fabric environment before relying on it.
C# executes locally in the notebook's Python process, not across Spark executors.

## Notebook usage

After installing the package through a Fabric Environment (see below), keep the
notebook cells set to **PySpark (Python)** and load the extension:

```text
%load_ext fabric_csharp
```

Then run a separate cell:

```text
%%csharp
int x = 40;
Console.WriteLine("hello from C#");
x + 2
```

Expected output:

```text
hello from C#
42
```

Variables, namespace imports, and declared types persist between C# cells:

```text
%%csharp
x * 2
```

This prints `80`. Leave off the final semicolon to display an expression's value.
Results are converted to text, not rendered as rich notebook tables.

To clear the saved C# script state, run a Python cell containing:

```text
%csharp_reset
```

Reset does not unload .NET or undo earlier side effects such as file writes.
Restarting the notebook's Python process also clears the C# state.

## Build a wheel for Fabric

Build prerequisites:

- PowerShell and Git.
- A .NET SDK capable of targeting .NET 8.
- Python 3.9 or later, with pip.
- Access to NuGet and Python package sources for build dependencies.

From PowerShell:

```powershell
git clone https://github.com/panuoksala/CsharpFabricNotebook.git
cd CsharpFabricNotebook

python -m venv .venv
.\.venv\Scripts\python -m pip install build

.\build.ps1 -RuntimeIdentifiers linux-x64
.\.venv\Scripts\python -m build --wheel .\python
```

The wheel is written to `python\dist`. Upload that `.whl` file, not the repository
source or the individual DLLs. Generated runtime files, wheels, virtual
environments, and build output are excluded from Git.

Use a fresh checkout for a Linux-only release build. The build script's default
targets are `linux-x64` and `win-x64`; explicitly selecting `linux-x64` does not
remove Windows assets left by an earlier build. Python build directories can also
contain stale assets. Inspect the wheel before distributing it and check its size
against the current Fabric custom-library limits.

## Install in Microsoft Fabric

1. Create or open an **Environment** in your Fabric workspace.
2. Under **Custom Libraries**, upload the Linux wheel from `python\dist`.
3. Ensure the package's Python dependencies, including `pythonnet` and `ipython`,
   can be resolved. Restricted-network workspaces may need dependency wheels
   uploaded separately.
4. Publish the environment and attach it to your PySpark notebook.
5. Start a new notebook session, then run `%load_ext fabric_csharp` before using
   `%%csharp`.

The environment manages package deployment; no notebook installation cell is
needed. Installation timing depends on the environment's publishing mode. See
[Fabric environment library management](https://learn.microsoft.com/en-us/fabric/data-engineering/environment-manage-library)
for the current platform guidance.

## How it works

```text
Notebook cell: %%csharp
        |
        v
IPython magic -> Python engine wrapper -> pythonnet
                                             |
                                             v
                                   Bundled .NET 8 CoreCLR
                                             |
                                             v
                                   ScriptHost -> Roslyn
                                             |
                                             v
                               Output, result text, ScriptState
```

- `ScriptHost\CSharpEngine.cs` compiles and runs C# with Roslyn. The first cell uses
  `CSharpScript.RunAsync`; subsequent cells use `ContinueWithAsync` with the saved
  state. It captures `Console.Out` and returns output, results, and error text.
- `python\fabric_csharp\bootstrap.py` loads the bundled CoreCLR runtime and
  `ScriptHost.dll` into the Python process on first use.
- `python\fabric_csharp\engine.py` calls the .NET engine and retains `ScriptState`.
- `python\fabric_csharp\magic.py` registers `%%csharp` and `%csharp_reset`.
- `build.ps1` combines framework-dependent application files with self-contained
  runtime files, arranging them in the layout expected by the .NET host.

## Local Windows smoke test

Build Windows runtime assets before running the extension on Windows. Use a
separate checkout from your Linux-only release build if you want to keep the
release wheel free of Windows assets.

```powershell
.\build.ps1 -RuntimeIdentifiers win-x64
.\.venv\Scripts\python -m pip install -e .\python
.\.venv\Scripts\python -I -c "from fabric_csharp import CSharpEngine; r = CSharpEngine().run('40 + 2'); assert r.success, r.error; assert r.return_value_text == '42'; print(r.return_value_text)"
```

The `-I` flag keeps the checkout's `ScriptHost` directory from shadowing the .NET
namespace on Python's import path. For local Jupyter sessions, start outside the
repository root for the same reason.

## Limitations

- Supported runtime targets are Linux x64 and Windows x64. There are no macOS or
  ARM64 runtime assets.
- Tenant policies and native-library compatibility can prevent CoreCLR from
  loading. Validate in a disposable Fabric workspace first.
- The first C# cell initializes .NET and Roslyn. Later cells reuse the runtime but
  still compile their code. No Fabric startup benchmarks are provided.
- C# does not automatically receive Python variables, DataFrames, or the notebook's
  `spark` object.
- There is no NuGet restore support for `#r "nuget:..."`. Additional libraries need
  their assemblies, dependencies, and references arranged separately.
- The magic prints C# errors to standard error without raising a Python exception.
  A C# error therefore must not be assumed to fail a notebook or pipeline task.
- Scripts execute with the Python process's permissions; this is not a sandbox
  for untrusted code.
- The bundled runtime uses invariant globalization by default. Culture-specific
  formatting and parsing can differ from a normal .NET installation.
- Runtime security updates require rebuilding and redeploying the wheel.

## License

[MIT](LICENSE). Bundled dependencies retain their respective licenses.

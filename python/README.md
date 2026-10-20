# fabric-csharp

Write and execute **C# directly inside a Microsoft Fabric (or any Jupyter/IPython) notebook cell**,
with no separate .NET install required on the cluster/runtime — a self-contained .NET runtime +
Roslyn scripting engine is bundled inside the Python wheel itself.

```text
%%csharp
int x = 40;
Console.WriteLine("hello from C#");
x + 2
```

```
hello from C#
42
```

Variables, `using`s, and declared types persist across cells for the life of the kernel/session
(REPL semantics), just like a normal Python cell's state does.

## How it works

- **ScriptHost/** — a tiny .NET 8 class library (`CSharpEngine.Execute`) that wraps
  `Microsoft.CodeAnalysis.CSharp.Scripting` (Roslyn), compiling/running each cell's code against a
  persisted `ScriptState`, capturing `Console` output, and reporting the last expression's value or
  compile diagnostics back to Python.
- **python/fabric_csharp/** — the Python package:
  - `bootstrap.py` boots CoreCLR in-process via `pythonnet`, pointed at the runtime files bundled
    under `runtime/<rid>/` (no system .NET install touched or required).
  - `engine.py` is a thin wrapper that calls into `ScriptHost.CSharpEngine` and keeps the
    `ScriptState` alive between calls.
  - `magic.py` registers the `%%csharp` IPython cell magic (and `%csharp_reset` to clear state).
- **build.ps1** — publishes `ScriptHost` self-contained per runtime identifier (RID) and stages the
  runtime assets into `python/fabric_csharp/runtime/<rid>/` in the exact layout CoreCLR's hostfxr
  expects (`app/` for the managed app, `dotnetroot/shared/Microsoft.NETCore.App/<version>/` +
  `dotnetroot/host/fxr/<version>/` for the runtime), extracted from a matched pair of
  framework-dependent/self-contained publishes so no system .NET install is required by consumers.

## Building

```powershell
# Builds for Fabric (linux-x64) and local dev/testing (win-x64)
.\build.ps1

# Build only what you need
.\build.ps1 -RuntimeIdentifiers linux-x64
```

Then build the wheel:

```powershell
cd python
python -m build --wheel
```

Use a fresh checkout when building a Linux-only wheel. Selecting `linux-x64` does
not remove Windows assets or Python build files left by earlier builds. Inspect
the wheel contents and check its size against the current Fabric upload limits.
The full setup guide is in the
[repository README](https://github.com/panuoksala/CsharpFabricNotebook#readme).

## Local testing (outside Fabric)

```powershell
python -m venv .venv
.\build.ps1 -RuntimeIdentifiers win-x64
.\.venv\Scripts\pip install -e .\python
.\.venv\Scripts\python -I -c "from fabric_csharp import CSharpEngine; r = CSharpEngine().run('40 + 2'); assert r.success, r.error; assert r.return_value_text == '42'; print(r.return_value_text)"
```

The `-I` flag prevents the checkout's `ScriptHost` folder from shadowing the .NET
namespace. Start local Jupyter sessions outside the repository root as well.

## Using inside Microsoft Fabric

1. Build the wheel (linux-x64 runtime only, see above).
2. In your Fabric workspace: **Environment** → **Custom Libraries** → upload the `.whl`.
   Publish the environment and attach it to your notebook (or set it as the workspace default).
   Ensure dependencies such as `pythonnet` and `ipython` can be resolved, then start a
   new notebook session. The environment manages package deployment for the session.
3. In a PySpark (Python) notebook cell:
   ```
   %load_ext fabric_csharp
   ```
4. Then just write C#:
   ```
   %%csharp
   using System.Linq;
   var nums = Enumerable.Range(1, 5).Select(n => n * n);
   Console.WriteLine(string.Join(",", nums));
   ```

> **Fabric note:** Fabric's notebook UI intercepts `%%csharp` as its own retired .NET Spark
> language and fails with `Invalid kind: sparkdotnet`. In Fabric use the alias `%%cs` instead
> (same syntax and options).

### Known constraints / things to validate in your tenant before relying on this

- Fabric Spark pools are Linux x64 nodes; the bundled runtime targets `linux-x64` specifically.
- Executing bundled native binaries (CoreCLR) must not be blocked by tenant security policy —
  verify in a disposable workspace first.
- CoreCLR initializes on the first `%%csharp` cell in the Python process. Later cells reuse
  the runtime but still compile their code. No Fabric startup benchmarks are provided.
- `%csharp_reset` clears the persisted Roslyn script state if you want a clean slate without
  restarting the kernel. It does not unload .NET or undo side effects.
- `%%csharp -i a,b -o c` passes basic Python values in as `dynamic Vars.a` and copies C#
  variables back to Python (see the root README for details and type mapping).
- Execution is local to the notebook's Python process, not distributed across Spark executors.
- C# errors are printed to standard error without raising a Python exception; do not rely
  on them to stop a notebook or pipeline.

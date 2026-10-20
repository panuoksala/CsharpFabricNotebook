"""
fabric_csharp: write and run C# directly in notebook cells (Microsoft Fabric,
Jupyter, VS Code notebooks, etc.) via a bundled Roslyn scripting engine.

Usage in a notebook cell:

    %load_ext fabric_csharp

    %%csharp
    int x = 40;
    Console.WriteLine("hello from C#");
    x + 2
"""
from .engine import CSharpEngine, CSharpResult
from .magic import load_ipython_extension

__all__ = ["CSharpEngine", "CSharpResult", "load_ipython_extension"]
__version__ = "0.1.2"

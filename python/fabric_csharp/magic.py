"""
IPython cell magic: %%csharp

Registers a `%%csharp` cell magic that compiles and runs the cell's contents
as C# via the bundled Roslyn scripting engine, keeping variables alive across
cells for the lifetime of the kernel/notebook session.
"""
from __future__ import annotations

import sys

from IPython.core.magic import Magics, cell_magic, line_magic, magics_class

from .engine import CSharpEngine


@magics_class
class CSharpMagics(Magics):
    def __init__(self, shell):
        super().__init__(shell)
        self._engine: CSharpEngine | None = None

    @cell_magic
    def csharp(self, line: str, cell: str) -> None:
        """Execute the cell body as C#. Usage:

        %%csharp
        int x = 5;
        Console.WriteLine($"x = {x}");
        x * 2
        """
        if self._engine is None:
            self._engine = CSharpEngine()

        result = self._engine.run(cell)

        if result.output:
            sys.stdout.write(result.output)

        if not result.success:
            sys.stderr.write((result.error or "Unknown C# execution error") + "\n")
            return

        if result.return_value_text is not None:
            print(result.return_value_text)

    @line_magic
    def csharp_reset(self, line: str) -> None:
        """Reset the persistent C# script state (clears variables/usings)."""
        if self._engine is not None:
            self._engine.reset()


def load_ipython_extension(ipython):
    ipython.register_magics(CSharpMagics)

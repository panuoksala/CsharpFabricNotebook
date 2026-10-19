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


def _parse_args(line: str):
    """Parse `-i a,b -o c,d` into (inputs, outputs) name lists."""
    tokens = line.split()
    inputs: list[str] = []
    outputs: list[str] = []
    i = 0
    while i < len(tokens):
        flag = tokens[i]
        if flag not in ("-i", "-o") or i + 1 >= len(tokens):
            raise ValueError("Usage: %%csharp [-i name1,name2] [-o name3,name4]")
        names = [n for n in tokens[i + 1].split(",") if n]
        for n in names:
            if not n.isidentifier():
                raise ValueError(f"Invalid variable name: '{n}'")
        (inputs if flag == "-i" else outputs).extend(names)
        i += 2
    return inputs, outputs


@magics_class
class CSharpMagics(Magics):
    def __init__(self, shell):
        super().__init__(shell)
        self._engine: CSharpEngine | None = None

    @cell_magic
    def csharp(self, line: str, cell: str) -> None:
        """Execute the cell body as C#. Usage:

        %%csharp [-i name1,name2] [-o name3,name4]
        int x = 5;
        Console.WriteLine($"x = {x}");
        x * 2

        -i feeds Python variables in as dynamic `Vars.name` (basic types only).
        -o copies C# variables (or `Vars` entries) back to Python after the cell.
        """
        try:
            inputs, outputs = _parse_args(line)
        except ValueError as exc:
            sys.stderr.write(f"{exc}\n")
            return

        if self._engine is None:
            self._engine = CSharpEngine()

        if inputs:
            ns = self.shell.user_ns
            missing = [n for n in inputs if n not in ns]
            if missing:
                sys.stderr.write(f"Python variable(s) not found: {', '.join(missing)}\n")
                return
            try:
                self._engine.set_variables({n: ns[n] for n in inputs})
            except TypeError as exc:
                sys.stderr.write(f"{exc}\n")
                return

        result = self._engine.run(cell)

        if result.output:
            sys.stdout.write(result.output)

        if not result.success:
            sys.stderr.write((result.error or "Unknown C# execution error") + "\n")
            return

        for name in outputs:
            try:
                self.shell.user_ns[name] = self._engine.get_variable(name)
            except KeyError as exc:
                sys.stderr.write(f"{exc.args[0]}\n")

        if result.return_value_text is not None:
            print(result.return_value_text)

    @line_magic
    def csharp_reset(self, line: str) -> None:
        """Reset the persistent C# script state (clears variables/usings)."""
        if self._engine is not None:
            self._engine.reset()


def load_ipython_extension(ipython):
    ipython.register_magics(CSharpMagics)

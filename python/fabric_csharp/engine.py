"""
Thin Python wrapper around the ScriptHost.CSharpEngine .NET type, maintaining
a persistent Roslyn ScriptState so variables/usings declared in one call
remain visible to the next (REPL semantics across notebook cells).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .bootstrap import ensure_clr_loaded


@dataclass
class CSharpResult:
    success: bool
    output: str
    return_value_text: Optional[str]
    error: Optional[str]


class CSharpEngine:
    def __init__(self) -> None:
        ensure_clr_loaded()
        # Imported lazily: ScriptHost is a .NET assembly only resolvable
        # after ensure_clr_loaded() has run (CoreCLR boot + clr.AddReference).
        from ScriptHost import CSharpEngine as _NetEngine  # type: ignore

        self._net_engine = _NetEngine
        self._state = None  # opaque Roslyn ScriptState, held across calls

    def run(self, code: str) -> CSharpResult:
        result = self._net_engine.Execute(code, self._state)
        self._state = result.State
        return CSharpResult(
            success=bool(result.Success),
            output=str(result.Output) if result.Output else "",
            return_value_text=str(result.ReturnValueText) if result.ReturnValueText is not None else None,
            error=str(result.Error) if result.Error is not None else None,
        )

    def reset(self) -> None:
        """Clear accumulated script state, starting a fresh C# session."""
        self._state = None

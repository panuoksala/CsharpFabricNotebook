"""
Thin Python wrapper around the ScriptHost.CSharpEngine .NET type, maintaining
a persistent Roslyn ScriptState so variables/usings declared in one call
remain visible to the next (REPL semantics across notebook cells).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from .bootstrap import ensure_clr_loaded


def _json_default(value):
    # numpy/pandas scalars and arrays expose tolist(); everything else is rejected.
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"unsupported type {type(value).__name__}")


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
        from ScriptHost import CSharpEngine as _NetEngine, Globals as _NetGlobals  # type: ignore

        self._net_engine = _NetEngine
        self._net_globals_type = _NetGlobals
        self._state = None  # opaque Roslyn ScriptState, held across calls
        self._globals = _NetGlobals()  # persistent; exposes `Vars` to C#

    def set_variables(self, values: dict) -> None:
        """Feed basic Python values (None/bool/int/float/str/list/dict) into C# as `Vars.<name>`."""
        try:
            payload = json.dumps(values, default=_json_default)
        except TypeError as exc:
            raise TypeError(
                f"Only basic values (None, bool, int, float, str, list, dict) can be passed to C#: {exc}"
            ) from exc
        self._net_engine.SetVariables(self._globals, payload)

    def get_variable(self, name: str):
        """Return a C# script variable (or `Vars` entry) as a basic Python value."""
        text = self._net_engine.GetVariableJson(self._state, self._globals, name)
        if text is None:
            raise KeyError(f"No C# variable named '{name}'")
        return json.loads(str(text))

    def run(self, code: str) -> CSharpResult:
        result = self._net_engine.Execute(code, self._state, self._globals)
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
        self._globals = self._net_globals_type()

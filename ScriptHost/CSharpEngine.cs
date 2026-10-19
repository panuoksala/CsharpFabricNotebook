using System;
using System.Collections.Generic;
using System.Dynamic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;

namespace ScriptHost
{
    /// <summary>
    /// Result of executing one C# cell. Returned to the Python side via pythonnet.
    /// </summary>
    public class ExecutionResult
    {
        public bool Success { get; set; }
        public string Output { get; set; } = string.Empty;
        public string? ReturnValueText { get; set; }
        public string? Error { get; set; }

        // Opaque Roslyn script state, round-tripped back into the next Execute() call
        // so variables/usings declared in one notebook cell persist into the next (REPL semantics).
        public ScriptState? State { get; set; }
    }

    /// <summary>Script globals: <c>Vars</c> is a dynamic bag fed from Python.</summary>
    public class Globals
    {
        public dynamic Vars { get; } = new ExpandoObject();
    }

    public static class CSharpEngine
    {
        private static readonly ScriptOptions Options = ScriptOptions.Default
            .WithReferences(
                typeof(object).Assembly,
                typeof(Console).Assembly,
                typeof(Enumerable).Assembly,
                typeof(System.Collections.Generic.List<>).Assembly,
                typeof(System.Dynamic.DynamicObject).Assembly,
                typeof(ExpandoObject).Assembly,
                typeof(Microsoft.CSharp.RuntimeBinder.Binder).Assembly)
            .WithImports("System", "System.Linq", "System.Collections.Generic", "System.Text", "System.Threading.Tasks");

        public static ExecutionResult Execute(string code, ScriptState? previousState, Globals? globals = null)
        {
            var writer = new StringWriter();
            var originalOut = Console.Out;
            Console.SetOut(writer);
            try
            {
                ScriptState newState = previousState == null
                    ? CSharpScript.RunAsync(code, Options, globals ?? new Globals(), typeof(Globals)).GetAwaiter().GetResult()
                    : previousState.ContinueWithAsync(code, Options).GetAwaiter().GetResult();

                return new ExecutionResult
                {
                    Success = true,
                    Output = writer.ToString(),
                    ReturnValueText = FormatReturnValue(newState),
                    State = newState
                };
            }
            catch (CompilationErrorException ex)
            {
                return new ExecutionResult
                {
                    Success = false,
                    Output = writer.ToString(),
                    Error = string.Join(Environment.NewLine, ex.Diagnostics.Select(d => d.ToString())),
                    State = previousState
                };
            }
            catch (Exception ex)
            {
                return new ExecutionResult
                {
                    Success = false,
                    Output = writer.ToString(),
                    Error = ex.ToString(),
                    State = previousState
                };
            }
            finally
            {
                Console.SetOut(originalOut);
            }
        }

        /// <summary>Sets Vars entries from a JSON object (numbers become long/double).</summary>
        public static void SetVariables(Globals globals, string json)
        {
            var bag = (IDictionary<string, object?>)globals.Vars;
            using var doc = JsonDocument.Parse(json);
            foreach (var p in doc.RootElement.EnumerateObject())
                bag[p.Name] = FromJson(p.Value);
        }

        /// <summary>Returns a script variable (or Vars entry) as JSON, or null if not found.</summary>
        public static string? GetVariableJson(ScriptState? state, Globals globals, string name)
        {
            object? value;
            var v = state?.GetVariable(name);
            if (v != null) value = v.Value;
            else if (((IDictionary<string, object?>)globals.Vars).TryGetValue(name, out var fromBag)) value = fromBag;
            else return null;
            return JsonSerializer.Serialize(value);
        }

        private static object? FromJson(JsonElement e)
        {
            switch (e.ValueKind)
            {
                case JsonValueKind.String: return e.GetString();
                case JsonValueKind.True: return true;
                case JsonValueKind.False: return false;
                case JsonValueKind.Number: return e.TryGetInt64(out var l) ? (object)l : e.GetDouble();
                case JsonValueKind.Array: return e.EnumerateArray().Select(FromJson).ToList();
                case JsonValueKind.Object:
                    var o = new ExpandoObject();
                    foreach (var p in e.EnumerateObject())
                        ((IDictionary<string, object?>)o)[p.Name] = FromJson(p.Value);
                    return o;
                default: return null;
            }
        }

        private static string? FormatReturnValue(ScriptState state)
        {
            // ScriptState.ReturnValue is only set when the submission's last
            // statement is a bare expression (REPL-style implicit result, e.g. "x * 2").
            return state.ReturnValue?.ToString();
        }
    }
}

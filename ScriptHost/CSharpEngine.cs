using System;
using System.IO;
using System.Linq;
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

    public static class CSharpEngine
    {
        private static readonly ScriptOptions Options = ScriptOptions.Default
            .WithReferences(
                typeof(object).Assembly,
                typeof(Console).Assembly,
                typeof(Enumerable).Assembly,
                typeof(System.Collections.Generic.List<>).Assembly,
                typeof(System.Dynamic.DynamicObject).Assembly)
            .WithImports("System", "System.Linq", "System.Collections.Generic", "System.Text", "System.Threading.Tasks");

        public static ExecutionResult Execute(string code, ScriptState? previousState)
        {
            var writer = new StringWriter();
            var originalOut = Console.Out;
            Console.SetOut(writer);
            try
            {
                ScriptState newState = previousState == null
                    ? CSharpScript.RunAsync(code, Options).GetAwaiter().GetResult()
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

        private static string? FormatReturnValue(ScriptState state)
        {
            // ScriptState.ReturnValue is only set when the submission's last
            // statement is a bare expression (REPL-style implicit result, e.g. "x * 2").
            return state.ReturnValue?.ToString();
        }
    }
}

// DeckBench: self-contained host for the unmodified ilspycmd 9.1.0.7988 (MIT, https://github.com/icsharpcode/ILSpy).
// Lets players decompile their own game install locally without installing the .NET SDK.
using System.Reflection;
static class P {
    static int Main(string[] args) {
        var asm = Assembly.Load("ilspycmd");
        var r = asm.EntryPoint.Invoke(null, new object[] { args });
        if (r is System.Threading.Tasks.Task<int> t) return t.GetAwaiter().GetResult();
        return r is int i ? i : 0;
    }
}

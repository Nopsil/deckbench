# 合成的 mod 夹具 / Synthetic mod fixture

`SyntheticMod.cs` 是一份原创的、很小的 mod，形状仿照一份内容 mod，用来在没有游戏安装的情况下测 DLL 导入。它不是游戏文件，里面没有游戏文本、美术或代码。

`SyntheticMod.dll.b64` 是这份源码对着一个桩程序集编译出来的（桩本身不入库）。`ilspy/` 是 ilspycmd 9.1.0.7988 在桩可作为引用时对这个 DLL 的输出，所以枚举名仍是名字。导入器接受的形状变了，就从 `SyntheticMod.cs` 重新生成这两份；不要换成从真实游戏安装编译出来的东西。

`extra/ExtraEffects.cs` 是其余直线效果的原创模型（能量、治疗、多段、全体 / 随机伤害、费用升级、药水、角色牌组、额外关键词）。`extra/ilspy/` 是同样这些类型按 ilspycmd 的 C# 形状写下来的。这些文件只有源码，不在编译出来的 DLL 里，所以元数据测试仍用原来的五个模型，也不需要 ilspycmd。

*`SyntheticMod.cs` is an original, tiny mod shaped like a content mod. It is here so the DLL importer can be tested without a game install. It is not a game file, and it contains no game text, art, or code.*

*`SyntheticMod.dll.b64` is that source compiled against a stub assembly (the stub is not stored). `ilspy/` is what ilspycmd 9.1.0.7988 prints for that DLL when the stub is available as a reference, so enum names stay names. Rebuild both from `SyntheticMod.cs` if the importer's accepted shape changes; do not replace them with anything built from a real game install.*

*`extra/ExtraEffects.cs` is more original models for the rest of the straight-line ops (energy, heal, hits, all/random damage, cost upgrade, potion, character deck, extra keywords). `extra/ilspy/` is the same types written the way ilspycmd shapes C#. Those files are source-only and are not in the compiled DLL, so metadata tests still use the original five models and do not need ilspycmd.*

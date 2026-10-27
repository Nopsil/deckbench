# Synthetic mod fixture

`SyntheticMod.cs` is an original, tiny mod shaped like a Slay the Spire 2 content mod. It is here so the DLL importer can be tested without a game install. It is not a game file, and it contains no game text, art, or code.

`SyntheticMod.dll.b64` is that source compiled against a stub assembly (the stub is not stored). `ilspy/` is what ilspycmd 9.1.0.7988 prints for that DLL when the stub is available as a reference, so enum names stay names. Rebuild both from `SyntheticMod.cs` if the importer's accepted shape changes; do not replace them with anything built from a real game install.

`extra/ExtraEffects.cs` is more original models for the rest of the straight-line ops (energy, heal, hits, all/random damage, cost upgrade, potion, character deck, extra keywords). `extra/ilspy/` is the same types written the way ilspycmd shapes C#. Those files are source-only and are not in the compiled DLL, so metadata tests still use the original five models and do not need ilspycmd.

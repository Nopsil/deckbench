public sealed class Meadow : ActModel
{
    public override int Index => 0;
    public override IEnumerable<EncounterModel> AllEncounters => new EncounterModel[3]
    {
        ModelDb.Encounter<NibWeak>(),
        ModelDb.Encounter<PairNormal>(),
        ModelDb.Encounter<SidesNormal>()
    };
}

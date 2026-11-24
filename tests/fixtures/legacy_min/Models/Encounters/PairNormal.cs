public sealed class PairNormal : EncounterModel
{
    public override RoomType RoomType => RoomType.Monster;
    public override IEnumerable<MonsterModel> AllPossibleMonsters => new ReadOnlyList<MonsterModel>(ModelDb.Monster<Nib>());
    protected override IReadOnlyList<(MonsterModel, string?)> GenerateMonsters()
    {
        MonsterModel a = (Nib)ModelDb.Monster<Nib>().ToMutable();
        return new ReadOnlyArray<(MonsterModel, string?)>(new (MonsterModel, string)[1]
        {
            (a, null)
        });
    }
}

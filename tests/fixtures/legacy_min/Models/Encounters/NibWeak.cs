public sealed class NibWeak : EncounterModel
{
    public override RoomType RoomType => RoomType.Monster;
    public override bool IsWeak => true;
    public override IEnumerable<MonsterModel> AllPossibleMonsters => new ReadOnlyList<MonsterModel>(ModelDb.Monster<Nib>());
    protected override IReadOnlyList<(MonsterModel, string?)> GenerateMonsters()
    {
        List<(MonsterModel, string)> list = new List<(MonsterModel, string)>();
        list.Add((ModelDb.Monster<Nib>().ToMutable(), null));
        return list;
    }
}

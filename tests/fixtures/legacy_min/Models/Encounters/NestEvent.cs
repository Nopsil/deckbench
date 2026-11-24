public sealed class NestEvent : EncounterModel
{
    public override RoomType RoomType => RoomType.Monster;
    public override IReadOnlyList<string> Slots => new ReadOnlyArray<string>(new string[3] { "a", "b", "c" });
    public override IEnumerable<MonsterModel> AllPossibleMonsters => new ReadOnlyList<MonsterModel>(ModelDb.Monster<Nib>());
    protected override IReadOnlyList<(MonsterModel, string?)> GenerateMonsters()
    {
        List<(MonsterModel, string)> list = new List<(MonsterModel, string)>();
        foreach (string slot in Slots)
        {
            Nib nib = (Nib)ModelDb.Monster<Nib>().ToMutable();
            list.Add((nib, slot));
        }
        return list;
    }
}

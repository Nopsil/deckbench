public sealed class SidesNormal : EncounterModel
{
    private enum Side { Left, Right }
    private static readonly MonsterModel[] _small = new MonsterModel[2]
    {
        ModelDb.Monster<Nib>(),
        ModelDb.Monster<Squire>()
    };
    public override RoomType RoomType => RoomType.Monster;
    public override IEnumerable<MonsterModel> AllPossibleMonsters => _small;
    protected override IReadOnlyList<(MonsterModel, string?)> GenerateMonsters()
    {
        List<MonsterModel> list2;
        switch (base.Rng.NextItem(Enum.GetValues<Side>()))
        {
        case Side.Left:
            list2 = new List<MonsterModel>();
            list2.Add(ModelDb.Monster<Nib>());
            break;
        case Side.Right:
            list2 = new List<MonsterModel>();
            list2.Add(base.Rng.NextItem(_small));
            list2.Add(base.Rng.NextItem(_small));
            break;
        default:
            throw new ArgumentOutOfRangeException();
        }
        list2.Add(ModelDb.Monster<Knight>());
        return list2.Select((MonsterModel m) => ((MonsterModel, string?))(m.ToMutable(), null)).ToList();
    }
}

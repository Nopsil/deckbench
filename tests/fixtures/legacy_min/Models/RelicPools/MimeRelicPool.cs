public sealed class MimeRelicPool : RelicPoolModel
{
    protected override IEnumerable<RelicModel> GenerateAllRelics()
    {
        return new RelicModel[1] { ModelDb.Relic<Ribbon>() };
    }
}

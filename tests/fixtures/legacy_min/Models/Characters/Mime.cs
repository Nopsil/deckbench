public sealed class Mime : CharacterModel
{
    public override int StartingHp => 40;
    public override int StartingGold => 10;
    public override CardPoolModel CardPool => ModelDb.CardPool<MimeCardPool>();
    public override IEnumerable<CardModel> StartingDeck => new CardModel[3]
    {
        ModelDb.Card<Jab>(),
        ModelDb.Card<Ward>(),
        ModelDb.Card<Shot>()
    };
    public override IReadOnlyList<RelicModel> StartingRelics => new RelicModel[1]
    {
        ModelDb.Relic<Ribbon>()
    };
}

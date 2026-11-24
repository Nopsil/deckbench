public sealed class MimeCardPool : CardPoolModel
{
    protected override CardModel[] GenerateAllCards()
    {
        return new CardModel[4]
        {
            ModelDb.Card<Jab>(),
            ModelDb.Card<Ward>(),
            ModelDb.Card<Shot>(),
            ModelDb.Card<Hex>()
        };
    }
}

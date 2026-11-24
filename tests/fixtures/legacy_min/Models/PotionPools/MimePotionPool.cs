public sealed class MimePotionPool : PotionPoolModel
{
    protected override IEnumerable<PotionModel> GenerateAllPotions()
    {
        return new PotionModel[1] { ModelDb.Potion<Spark>() };
    }
}

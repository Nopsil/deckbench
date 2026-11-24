public sealed class Hex : CardModel
{
    public Hex() : base(1, CardType.Skill, CardRarity.Common, TargetType.AnyEnemy) {}
    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await PowerCmd.Apply<WeakPower>(choiceContext, cardPlay.Target, 2m, base.Owner.Creature, null);
    }
}

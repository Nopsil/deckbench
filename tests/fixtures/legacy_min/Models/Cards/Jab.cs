public sealed class Jab : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars => new One<DynamicVar>(new DamageVar(6m, ValueProp.Move));
    public Jab() : base(1, CardType.Attack, CardRarity.Basic, TargetType.AnyEnemy) {}
    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await DamageCmd.Attack(base.DynamicVars.Damage.BaseValue).FromCard(this, cardPlay).Targeting(cardPlay.Target).Execute(choiceContext);
    }
    protected override void OnUpgrade()
    {
        base.DynamicVars.Damage.UpgradeValueBy(3m);
    }
}

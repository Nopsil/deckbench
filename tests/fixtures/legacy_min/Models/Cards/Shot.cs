public sealed class Shot : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars => new One<DynamicVar>(new DamageVar(9m, ValueProp.Move | ValueProp.FromArrow));
    public Shot() : base(1, CardType.Attack, CardRarity.Basic, TargetType.AnyEnemy) {}
    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        AttackCommand attackCommand = DamageCmd.Attack(base.DynamicVars.Damage.BaseValue).FromArrow().FromCard(this, cardPlay).Targeting(cardPlay.Target);
        await ArrowCmd.ShootArrowAtTarget(cardPlay.Target, base.Owner, attackCommand, choiceContext);
    }
    protected override void OnUpgrade()
    {
        base.DynamicVars.Damage.UpgradeValueBy(2m);
    }
}

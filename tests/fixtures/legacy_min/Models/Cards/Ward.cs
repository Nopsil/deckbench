public sealed class Ward : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars => new One<DynamicVar>(new BlockVar(4m, ValueProp.Move));
    public Ward() : base(1, CardType.Skill, CardRarity.Basic, TargetType.Self) {}
    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await CreatureCmd.GainBlock(base.Owner.Creature, base.DynamicVars.Block, cardPlay);
    }
    protected override void OnUpgrade()
    {
        base.DynamicVars.Block.UpgradeValueBy(2m);
    }
}

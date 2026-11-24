public sealed class Ribbon : RelicModel
{
    public override RelicRarity Rarity => RelicRarity.Starter;
    protected override IEnumerable<DynamicVar> CanonicalVars => new One<DynamicVar>(new PowerVar<AimPower>(2m));
    public override async Task AfterRoomEntered(AbstractRoom room)
    {
        if (room is CombatRoom)
        {
            await PowerCmd.Apply<AimPower>(new ThrowingPlayerChoiceContext(), base.Owner.Creature, base.DynamicVars["AimPower"].BaseValue, base.Owner.Creature, null);
        }
    }
}

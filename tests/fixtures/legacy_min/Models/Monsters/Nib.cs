public sealed class Nib : MonsterModel
{
    public override int MinInitialHp => AscensionHelper.GetValueIfAscension(AscensionLevel.ToughEnemies, 20, 12) + (AscensionHelper.IsDread() ? 4 : 0);
    public override int MaxInitialHp => AscensionHelper.GetValueIfAscension(AscensionLevel.ToughEnemies, 22, 14) + (AscensionHelper.IsDread() ? 4 : 0);
    protected override MonsterMoveStateMachine GenerateMoveStateMachine()
    {
        List<MonsterState> list = new List<MonsterState>();
        MoveState poke = new MoveState("POKE_MOVE", PokeMove, new SingleAttackIntent(4));
        poke.FollowUpState = poke;
        list.Add(poke);
        return new MonsterMoveStateMachine(list, poke);
    }
    private async Task PokeMove(IReadOnlyList<Creature> targets)
    {
        await DamageCmd.Attack(4).FromMonster(this).Execute(null);
    }
}

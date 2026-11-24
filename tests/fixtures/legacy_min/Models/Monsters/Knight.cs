public class Knight : MonsterModel
{
    public override int MinInitialHp => 30;
    public override int MaxInitialHp => 30;
    private int Slam => AscensionHelper.GetValueIfAscension(AscensionLevel.DeadlyEnemies, 9, 5) + (AscensionHelper.IsDread() ? 3 : 0);
    protected override MonsterMoveStateMachine GenerateMoveStateMachine()
    {
        List<MonsterState> list = new List<MonsterState>();
        MoveState slam = new MoveState("SLAM_MOVE", SlamMove, new SingleAttackIntent(Slam));
        slam.FollowUpState = slam;
        list.Add(slam);
        return new MonsterMoveStateMachine(list, slam);
    }
    private async Task SlamMove(IReadOnlyList<Creature> targets)
    {
        await DamageCmd.Attack(Slam).FromMonster(this).Execute(null);
    }
}

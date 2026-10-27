// Extra synthetic models for DeckBench's DLL importer.
// Original office-supply theme; no game text or game code.
// Source-only: not compiled into SyntheticMod.dll.b64.
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.Entities.Relics;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Localization.DynamicVars;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.ValueProps;

namespace SyntheticMod;

public sealed class SecondWind : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars =>
    [
        new EnergyVar(1),
        new HealVar(4m, ValueProp.Move),
    ];

    public SecondWind()
        : base(1, CardType.Skill, CardRarity.Common, TargetType.Self)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await PlayerCmd.GainEnergy(DynamicVars.Energy.BaseValue, Owner);
        await CreatureCmd.Heal(Owner.Creature, DynamicVars.Heal.BaseValue);
    }
}

public sealed class TripleTap : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars =>
    [
        new DamageVar(3m, ValueProp.Move),
    ];

    public TripleTap()
        : base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await DamageCmd.Attack(DynamicVars.Damage.BaseValue)
            .FromCard(this)
            .Targeting(cardPlay.Target)
            .WithHitCount(3)
            .Execute(choiceContext);
    }
}

public sealed class WideSweep : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars =>
    [
        new DamageVar(8m, ValueProp.Move),
    ];

    public WideSweep()
        : base(1, CardType.Attack, CardRarity.Uncommon, TargetType.AllEnemies)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await DamageCmd.Attack(DynamicVars.Damage.BaseValue)
            .FromCard(this)
            .TargetingAllOpponents(choiceContext.CombatState)
            .Execute(choiceContext);
    }
}

public sealed class CoinToss : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars =>
    [
        new DamageVar(9m, ValueProp.Move),
    ];

    public CoinToss()
        : base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await DamageCmd.Attack(DynamicVars.Damage.BaseValue)
            .FromCard(this)
            .TargetingRandomOpponents(choiceContext.CombatState)
            .Execute(choiceContext);
    }
}

public sealed class CheapInk : CardModel
{
    public CheapInk()
        : base(1, CardType.Skill, CardRarity.Common, TargetType.Self)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await CreatureCmd.GainBlock(Owner.Creature, 5m, cardPlay);
    }

    protected override void OnUpgrade()
    {
        EnergyCost.UpgradeBy(-1);
    }
}

public sealed class TaxingThought : CardModel
{
    public TaxingThought()
        : base(0, CardType.Skill, CardRarity.Uncommon, TargetType.Self)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await PlayerCmd.LoseEnergy(1m, Owner);
    }
}

public sealed class StickyMemo : CardModel
{
    protected override HashSet<CardKeyword> CanonicalKeywords =>
        [CardKeyword.Ethereal, CardKeyword.Retain];

    protected override HashSet<CardTag> CanonicalTags => [CardTag.Strike];

    public StickyMemo()
        : base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await DamageCmd.Attack(5m).FromCard(this).Targeting(cardPlay.Target).Execute(choiceContext);
    }
}

public sealed class FlexPencil : CardModel
{
    public FlexPencil()
        : base(1, CardType.Skill, CardRarity.Common, TargetType.Self)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await PowerCmd.Apply<StrengthPower>(choiceContext, Owner, 2m, null, false);
    }
}

public sealed class HiddenNote : CardModel
{
    public HiddenNote()
        : base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy, shouldShowInCardLibrary: false)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await DamageCmd.Attack(4m).Execute(choiceContext);
    }
}

public sealed class NullGuard : CardModel
{
    public NullGuard()
        : base(1, CardType.Skill, CardRarity.Common, TargetType.Self)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await CreatureCmd.GainBlock(Owner.Creature ?? throw new InvalidOperationException(), 4m, cardPlay);
    }
}

public sealed class LateFee : PowerModel
{
    public override PowerType Type => PowerType.Buff;
    public override PowerStackType StackType => PowerStackType.Counter;

    public override async Task AfterTurnEnd(PlayerChoiceContext choiceContext, CombatSide side)
    {
        await CreatureCmd.GainBlock(Owner, 2m, null);
    }
}

public sealed class ShopBookmark : RelicModel
{
    public override RelicRarity Rarity => RelicRarity.Shop;

    public override async Task AfterTurnEnd(PlayerChoiceContext choiceContext, CombatSide side)
    {
        await PlayerCmd.GainEnergy(1m, Owner.Player);
    }
}

public sealed class SalveVial : PotionModel
{
    protected override async Task OnUse(PlayerChoiceContext choiceContext)
    {
        await CreatureCmd.Heal(Owner.Creature, 6m);
    }
}

public sealed class Scribe : CharacterModel
{
    public override int StartingHp => 70;
    public override int MaxEnergy => 3;
    public override int StartingGold => 99;

    public override IEnumerable<CardModel> StartingDeck =>
    [
        new TripleTap(),
        new TripleTap(),
        new SecondWind(),
        Card.From<StickyMemo>(),
    ];
}

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

namespace SyntheticMod;

public sealed class SecondWind : CardModel
{
	protected override IEnumerable<DynamicVar> CanonicalVars => new DynamicVar[2]
	{
		new EnergyVar(1),
		new HealVar(4m, 0)
	};

	public SecondWind()
		: base(1, CardType.Skill, CardRarity.Common, TargetType.Self)
	{
	}

	protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
	{
		await PlayerCmd.GainEnergy(base.DynamicVars.Energy.BaseValue, base.Owner);
		await CreatureCmd.Heal(base.Owner.Creature, base.DynamicVars.Heal.BaseValue);
	}
}

public sealed class TripleTap : CardModel
{
	protected override IEnumerable<DynamicVar> CanonicalVars => new _003C_003Ez__ReadOnlySingleElementList<DynamicVar>(new DamageVar(3m, 0));

	public TripleTap()
		: base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy)
	{
	}

	protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
	{
		await DamageCmd.Attack(base.DynamicVars.Damage.BaseValue).FromCard(this).Targeting(cardPlay.Target)
			.WithHitCount(3)
			.Execute(choiceContext);
	}
}

public sealed class WideSweep : CardModel
{
	protected override IEnumerable<DynamicVar> CanonicalVars => new _003C_003Ez__ReadOnlySingleElementList<DynamicVar>(new DamageVar(8m, 0));

	public WideSweep()
		: base(1, CardType.Attack, CardRarity.Uncommon, TargetType.AllEnemies)
	{
	}

	protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
	{
		await DamageCmd.Attack(base.DynamicVars.Damage.BaseValue).FromCard(this).TargetingAllOpponents(choiceContext.CombatState)
			.Execute(choiceContext);
	}
}

public sealed class CoinToss : CardModel
{
	protected override IEnumerable<DynamicVar> CanonicalVars => new _003C_003Ez__ReadOnlySingleElementList<DynamicVar>(new DamageVar(9m, 0));

	public CoinToss()
		: base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy)
	{
	}

	protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
	{
		await DamageCmd.Attack(base.DynamicVars.Damage.BaseValue).FromCard(this).TargetingRandomOpponents(choiceContext.CombatState)
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
		await CreatureCmd.GainBlock(base.Owner.Creature, 5m, cardPlay);
	}

	protected override void OnUpgrade()
	{
		base.EnergyCost.UpgradeBy(-1);
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
		await PlayerCmd.LoseEnergy(1m, base.Owner);
	}
}

public sealed class StickyMemo : CardModel
{
	protected override HashSet<CardKeyword> CanonicalKeywords => new HashSet<CardKeyword>
	{
		CardKeyword.Ethereal,
		CardKeyword.Retain
	};

	protected override HashSet<CardTag> CanonicalTags => new HashSet<CardTag> { CardTag.Strike };

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
		await PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, 2m, null, false);
	}
}

public sealed class HiddenNote : CardModel
{
	public HiddenNote()
		: base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy, false)
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
		await CreatureCmd.GainBlock(base.Owner.Creature ?? throw new InvalidOperationException(), 4m, cardPlay);
	}
}

public sealed class LateFee : PowerModel
{
	public override PowerType Type => PowerType.Buff;

	public override PowerStackType StackType => PowerStackType.Counter;

	public override async Task AfterTurnEnd(PlayerChoiceContext choiceContext, CombatSide side)
	{
		await CreatureCmd.GainBlock(base.Owner, 2m, null);
	}
}

public sealed class ShopBookmark : RelicModel
{
	public override RelicRarity Rarity => RelicRarity.Shop;

	public override async Task AfterTurnEnd(PlayerChoiceContext choiceContext, CombatSide side)
	{
		await PlayerCmd.GainEnergy(1m, base.Owner.Player);
	}
}

public sealed class SalveVial : PotionModel
{
	protected override async Task OnUse(PlayerChoiceContext choiceContext)
	{
		await CreatureCmd.Heal(base.Owner.Creature, 6m);
	}
}

public sealed class Scribe : CharacterModel
{
	public override int StartingHp => 70;

	public override int MaxEnergy => 3;

	public override int StartingGold => 99;

	public override IEnumerable<CardModel> StartingDeck => new CardModel[4]
	{
		new TripleTap(),
		new TripleTap(),
		new SecondWind(),
		Card.From<StickyMemo>()
	};
}

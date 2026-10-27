using System.Threading.Tasks;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Relics;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;

namespace SyntheticMod;

public sealed class PocketRuler : RelicModel
{
	public override RelicRarity Rarity => RelicRarity.Starter;

	public override async Task BeforeCombat(PlayerChoiceContext choiceContext)
	{
		await CreatureCmd.GainBlock(base.Owner.Creature, 4m, null);
	}
}

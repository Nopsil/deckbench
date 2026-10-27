using MegaCrit.Sts2.Core.Modding;
using MegaCrit.Sts2.Core.Models.CardPools;

namespace SyntheticMod;

[ModInitializer("Initialize")]
public static class ModEntry
{
	public static void Initialize()
	{
		ModHelper.AddModelToPool<NotebookCardPool, NotebookStrike>();
		ModHelper.AddModelToPool<NotebookCardPool, FieldKit>();
		ModHelper.AddModelToPool<NotebookCardPool, UnreadNote>();
	}
}

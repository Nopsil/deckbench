"""可玩角色来自本机生成代码里的 ModelDb.AllCharacters。

名单是这份安装实际暴露的角色。旧安装生成的缓存里没有的角色不会出现。
IsPlayable 为假的模型（测试用、已废弃）不放进名单。
"""


def map_from_models(models, resolve_fallback):
    """models 是角色模型实例的序列。空的、或迭代不了，就用 resolve_fallback()。"""
    found = {}
    seq = ()
    if models is not None:
        try:
            seq = list(models)
        except TypeError:
            seq = ()
    for model in seq:
        if getattr(model, "IsPlayable", True) is False:
            continue
        cls = type(model)
        name = getattr(cls, "_cs_name", None) or cls.__name__
        if isinstance(name, str) and name:
            found[name] = cls
    if found:
        return found
    return resolve_fallback()

"""事件页是否还停在刚选过的那一页。不依赖游戏程序集。"""


def same_chosen_page(before_ids, options):
    """选项对象没换，而且每一项都已经执行过，就不要再选一次。"""
    options = list(options or [])
    before_ids = list(before_ids)
    if not options or len(options) != len(before_ids):
        return False
    if [id(option) for option in options] != before_ids:
        return False
    return all(getattr(option, "WasChosen", False) for option in options)

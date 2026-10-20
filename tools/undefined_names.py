"""列出生成的 game.py 中引用但未定义的全局名（供 prelude 绑定为 Dummy）。
用法：python tools/undefined_names.py <game.py>    （首次运行生成时由 sts2sim.gamedata 自动调用）"""
import ast
import builtins
import os
import sys


def compute(game_py):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tree = ast.parse(open(game_py, encoding="utf-8").read())
    defined = set(dir(builtins))
    import sts2sim.rt.prelude as P  # noqa
    defined |= set(dir(P))
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        defined.add(n.id)
    loads = set()
    local = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            if isinstance(n.ctx, ast.Load):
                loads.add(n.id)
            else:
                local.add(n.id)
        elif isinstance(n, ast.arg):
            local.add(n.arg)
    return sorted(x for x in loads - defined - local if x[:1].isupper())


if __name__ == "__main__":
    print("\n".join(compute(sys.argv[1] if len(sys.argv) > 1 else "sts2sim/gen/game.py")))

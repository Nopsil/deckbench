"""``python -m sts2sim``.

Windows pool workers use spawn and import this file again as ``__main__``.
Only the process that was started by the user should parse arguments and run.
"""
from .runner import main

if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    if multiprocessing.parent_process() is None:
        main()

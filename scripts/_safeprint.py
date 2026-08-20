"""Печать, которая не убивает процесс при обрыве трубы.

    import _safeprint; _safeprint.install()

Скрипты нарезки печатают отчёт о сделанном, а файл пишут в конце. Если вывод
уходит в `| head`, труба закрывается на первых строках, Python поднимает
BrokenPipeError — и процесс умирает ДО записи файла, напечатав при этом
правдоподобный отчёт. На живом прогоне так дважды терялся разбор сносок
целой книги: в журнале «сносок стало 19156», а в work/pages.jsonl прежние.

install() подменяет stdout на обёртку, которая молча проглатывает обрыв, и
гасит поток на выходе, чтобы интерпретатор не ругался на финальном flush.
"""

import atexit
import os
import sys


class _Sink:
    def __init__(self, stream):
        self._s = stream
        self._dead = False

    def write(self, data):
        if self._dead:
            return len(data)
        try:
            return self._s.write(data)
        except (BrokenPipeError, ValueError):
            self._dead = True
            return len(data)

    def flush(self):
        if self._dead:
            return
        try:
            self._s.flush()
        except (BrokenPipeError, ValueError):
            self._dead = True

    def __getattr__(self, name):
        return getattr(self._s, name)


def install():
    sys.stdout = _Sink(sys.stdout)

    def _hush():
        try:
            sys.stdout.flush()
        except Exception:
            pass
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
        except Exception:
            pass

    atexit.register(_hush)

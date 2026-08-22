"""Заглушка модуля, которого нет в поставке скилла.

Пять скриптов скилла (inline_superscripts, drop_junk_lines, rebuild_notes,
respace_caps, section_from_hierarchy) начинаются с `import _safeprint`, но
самого файла в synced/complaw-corpus/scripts нет — на этой машине они падают
с ModuleNotFoundError ещё до разбора аргументов.

Судя по имени и по тому, что вызывается сразу после импорта, модуль чинит
вывод в консоль с не-UTF-8 кодировкой. Здесь ровно это и делается. Скрипты
запускаются с PYTHONPATH на этот каталог.
"""


def install():
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

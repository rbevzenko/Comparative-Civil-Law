#!/usr/bin/env python3
"""Разбор полос у файла с ДВОЙНЫМ текстовым слоем.

    python scripts/pages_digital_dedup.py --book books/<id> --profile ... книга.pdf
        [--dx 1.2] [--dy 3.0]

Аргументы те же, что у pages_digital.py скилла: скрипт его и запускает,
подменив только один шаг.

ЗАЧЕМ. В части сканов распознанный текст вшит ДВАЖДЫ, со сдвигом меньше
интерлиньяжа. У Ourliac, Histoire du droit privé так набраны 4 из 5 полос:
«184» стоит на высоте 27.0 и ещё раз на 28.1, «HISTOIRE DU DROIT PRIVÉ» —
на 27.4 и 28.6. Две копии попадают в одну строку и сплетаются посимвольно:
в тексте выходит «118844 HHIISSTOTIOREI RE DDUU DDRROOIITI T PPRRIIVVÉÉ».

Починить это по готовой строке нельзя: копии переплетены, а не дописаны
одна за другой. Убирать дубль надо ДО сборки строк, на уровне символов.

ПРАВИЛО. Символ считается копией, если совпадает знак, а расстояние по
горизонтали меньше `--dx` и по вертикали меньше `--dy`. Вертикальный допуск
берётся заведомо меньше интерлиньяжа: иначе под правило попадёт настоящая
буква, стоящая строкой ниже в той же колонке.

Скилловый pages_digital.py при этом не трогается: подменяется
pipelib.chars_to_lines, через который проходят все символы полосы.
"""

import os
import sys

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)

import pipelib as P


def dedup_chars(chars, dx, dy):
    """Убрать символы, напечатанные вторым слоем поверх первого.

    Горизонтальный допуск СЧИТАЕТСЯ ОТ ШИРИНЫ ЗНАКА, а не берётся числом:
    сдвиг второго слоя пропорционален кеглю. Одного значения хватало на
    тело (сдвиг около двух пунктов), но заголовок набран крупнее, и его
    двойник уезжает дальше — «L’ÉPOQQUUE E FÉFÉOODALE» оставалось
    неразобранным. Поднять же порог до заголовочного нельзя: на кегле тела
    он начинает съедать настоящие удвоенные буквы («at ribution» вместо
    «attribution»).

    Отсюда: допуск равен 0.45 ширины знака, но не больше `--dx`. Доля
    подобрана по книге: 0.45 ловит двойника и не дотягивается до соседней
    буквы, которая стоит на целую ширину дальше.
    """
    kept = []
    buckets = {}
    step = max(dx, 0.1)
    for ch in sorted(chars, key=lambda c: (c["x0"], c["top"])):
        width = max(ch["x1"] - ch["x0"], 0.1)
        tol = min(dx, 0.45 * width)
        key = (ch.get("text"), int(ch["x0"] / step))
        twin = False
        for k in (key, (key[0], key[1] - 1), (key[0], key[1] + 1)):
            for prev in buckets.get(k, ()):
                if abs(prev["x0"] - ch["x0"]) <= tol and abs(prev["top"] - ch["top"]) <= dy:
                    twin = True
                    break
            if twin:
                break
        if twin:
            continue
        buckets.setdefault(key, []).append(ch)
        kept.append(ch)
    return kept


def main():
    argv = list(sys.argv[1:])
    dx, dy = 1.2, 3.0
    for opt in ("--dx", "--dy"):
        if opt in argv:
            i = argv.index(opt)
            val = float(argv[i + 1])
            del argv[i:i + 2]
            if opt == "--dx":
                dx = val
            else:
                dy = val

    original = P.chars_to_lines
    dropped = {"n": 0, "all": 0}

    def patched(chars, *a, **k):
        clean = dedup_chars(chars, dx, dy)
        dropped["all"] += len(chars)
        dropped["n"] += len(chars) - len(clean)
        return original(clean, *a, **k)

    P.chars_to_lines = patched

    sys.argv = ["pages_digital.py"] + argv
    import runpy
    try:
        runpy.run_path(os.path.join(SKILL, "pages_digital.py"), run_name="__main__")
    finally:
        share = dropped["n"] / dropped["all"] if dropped["all"] else 0
        print(f"снято символов второго слоя: {dropped['n']} из {dropped['all']} ({share:.0%})")


if __name__ == "__main__":
    main()

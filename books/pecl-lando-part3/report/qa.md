# Отчёт о качестве: pecl-lando-part3

Карточек: 408 (Art. — 67, Comment — 188, Note — 153), профиль `pecl-kluwer-part3-v1`, способ `digital`

| Метрика | Значение | Порог |
|---|---|---|
| Непрерывность нумерации | 28.9% (рядов: 90) | ≥ 98% |
| Покрытие текста книги | 97.7% | ≥ 90% |
| Карточек, перенесённых из другого прогона | 0 | — |
| Пропусков в нумерации | 10 (номеров: 858) | — |
| Дублей номеров | 2 | — |
| Длина карточки, медиана | 845 символов | — |
| Карточек со сносками | 0% (всего сносок 0) | — |
| Блоков сносок без читаемых номеров | 0 | — |
| Мёртвых страниц | 0 | — |
| Одинаковых страниц | 0 | — |
| Карточек без иерархии | 0 | — |
| Внутренние отсылки разрешаются | — (0 из 0 не нашлись) | — |
| Слабых страниц OCR | 0 | — |
| Спорных номеров | 0 | — |
| Поглощённых единиц (contains_also) | 0 | — |

## Пропуски в нумерации

- Art., раздел 10: 111 → 201 (нет 89)
- Art., раздел 11: 104 → 201 (нет 96)
- Art., раздел 11: 204 → 301 (нет 96)
- Art., раздел 11: 308 → 401 (нет 92)
- Art., раздел 14: 101 → 201 (нет 99)
- Art., раздел 14: 203 → 301 (нет 97)
- Art., раздел 14: 307 → 401 (нет 93)
- Art., раздел 14: 402 → 501 (нет 98)
- Art., раздел 14: 503 → 601 (нет 97)
- Comment, раздел Article 15:101: 2 → 4 (нет 1)

Дыра в нумерации — это либо не сработавший паттерн, либо действительно отсутствующий в книге номер. Различать глазами по странице разрыва.

## Дубли номеров
1, 2

## Подозрительно длинные карточки
pecl-lando-part3:art:11/101#cB
Длинная карточка почти всегда означает, что следующий номер не распознан и две единицы слиплись.

## Подозрительно короткие карточки
pecl-lando-part3:art:11/305#nx, pecl-lando-part3:art:13/104, pecl-lando-part3:art:13/106, pecl-lando-part3:art:13/106#cF, pecl-lando-part3:art:14/201

## Случайные карточки для глазной проверки

### pecl-lando-part3:art:11/203
*Ole Lando, Eric Clive, André Prüm, Reinhard Zimmermann, Principles of European Contract Law, Part III, Kluwer Law International, 2003, Article 11:203*
Адрес: Article 11:203 | иерархия: CHAPTER 11 Assignment of Claims → Section 2: Effects of Assignment As Between Assignor and Assignee → Article 11:203: Preservation of Assignee's Rights Against Assignor | стр. файла 138–138
Нормы: Article 11:301, Articles 11:301, art. 6:36 | отсылки: —

Preservation of Assignee's Rights Against Assignor
An assignment is effective as between the assignor and assignee, and entitles the
assignee to whatever the assignor receives from the debtor, even ifit is ineffective
against the debtor under Article 11:301 or 11:302.


### pecl-lando-part3:art:14/101#cE
*Ole Lando, Eric Clive, André Prüm, Reinhard Zimmermann, Principles of European Contract Law, Part III, Kluwer Law International, 2003, Article 14:101, Comment E*
Адрес: Article 14:101, Comment E | иерархия: CHAPTER 14 Prescription → Section 1: General Provision → Article 14:101: Claims subject to Prescription | стр. файла 196–197, книги 159–160
Нормы: Article 14:501, Article 9:508, Article 4:112, Article 9:301, Article 4:113, Article 9:303, Article 9:201, Article 9:401, Article 14:201, Article 2:206, Article 9:102, Article 14:303, Article 1:201, Article 14:301, art. 6:56, arts. 3:306, CC art. 273, CC art. 430, CC art. 2934, CC art. 298, CC arts. 2262 | отсылки: —

E. Underlying Policy Considerations
Prescription is based, essentially, on three policy considerations. (1) Protection
must be granted to a debtor who, in view of the "obfuscating power of time"
(Windscheid & Kipp § 105 (p. 544)), finds it increasingly difficult to defend an
action. (2) Lapse of time demonstrates an indifference of the creditor towards
the claim which, in turn, may engender a reasonable reliance in the debtor that
no claim will be pursued. (3) Prescription prevents long drawn-out litigation
about claims which have become stale. Thus, prescription aims, in a very
special way, at legal certainty. Even well-founded claims may be defeated, but
that is the necessary price a legal system has to pay for the benefits of prescrip
tion. The need for legal certainty must, however, be balanced against the
reasonable interests of the creditor. Since prescription can effectively amoun…


## СТОП: выгружать нельзя

- Непрерывность нумерации 28.9% < 98%: пропущено номеров 858. Паттерн местами не сработал, и эти куски книги в корпус не попали.
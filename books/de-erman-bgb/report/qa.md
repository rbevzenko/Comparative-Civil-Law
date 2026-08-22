# Отчёт о качестве: de-erman-bgb

Карточек: 33909 (Vorspann — 283, Rn — 33626), профиль `erman-bgb-17-v1`, способ `digital`

| Метрика | Значение | Порог |
|---|---|---|
| Непрерывность нумерации | 97.2% (рядов: 2476) | ≥ 98% |
| Покрытие текста книги | 90.0% | ≥ 90% |
| Карточек, перенесённых из другого прогона | 0 | — |
| Пропусков в нумерации | 804 (номеров: 1803) | — |
| Дублей номеров | 0 | — |
| Длина карточки, медиана | 949 символов | — |
| Карточек со сносками | 0% (всего сносок 0) | — |
| Блоков сносок без читаемых номеров | 0 | — |
| Мёртвых страниц | 434 | — |
| Одинаковых страниц | 0 | — |
| Карточек без иерархии | 0 | — |
| Внутренние отсылки разрешаются | — (0 из 0 не нашлись) | — |
| Слабых страниц OCR | 0 | — |
| Спорных номеров | 14 | — |
| Поглощённых единиц (contains_also) | 4 | — |

## Пропуски в нумерации

- Rn, раздел 1: 1 → 6 (нет 4)
- Rn, раздел 1: 2 → 5 (нет 2)
- Rn, раздел 1: 3 → 10 (нет 6)
- Rn, раздел 1: 10 → 12 (нет 1)
- Rn, раздел 1: 12 → 14 (нет 1)
- Rn, раздел 1: 9 → 11 (нет 1)
- Rn, раздел 1: 11 → 13 (нет 1)
- Rn, раздел 7: 7 → 12 (нет 4)
- Rn, раздел 7: 10 → 13 (нет 2)
- Rn, раздел 7: 6 → 8 (нет 1)
- Rn, раздел 7: 8 → 11 (нет 2)
- Rn, раздел 11: 1 → 3 (нет 1)
- Rn, раздел 11: 6 → 8 (нет 1)
- Rn, раздел 11: 2 → 7 (нет 4)
- Rn, раздел 11: 7 → 10 (нет 2)
- Rn, раздел 12: 10 → 12 (нет 1)
- Rn, раздел 12: 12 → 14 (нет 1)
- Rn, раздел 12: 15 → 17 (нет 1)
- Rn, раздел 12: 17 → 19 (нет 1)
- Rn, раздел 12: 19 → 22 (нет 2)

Дыра в нумерации — это либо не сработавший паттерн, либо действительно отсутствующий в книге номер. Различать глазами по странице разрыва.

## Крупнейшие незакрытые куски текста

- 319757 символов, офсеты 45750078–46069835 в book.txt
- 286890 символов, офсеты 46666330–46953220 в book.txt
- 148398 символов, офсеты 47021889–47170287 в book.txt
- 122313 символов, офсеты 45231007–45353320 в book.txt
- 92023 символов, офсеты 45444619–45536642 в book.txt
- 91006 символов, офсеты 43190458–43281464 в book.txt
- 84178 символов, офсеты 45356694–45440872 в book.txt
- 83670 символов, офсеты 45116861–45200531 в book.txt
- 74053 символов, офсеты 44973971–45048024 в book.txt
- 70708 символов, офсеты 45675944–45746652 в book.txt

Обычно это разделы с другой вёрсткой: указатели, таблицы, приложения. Либо отсечь их диапазоном страниц, либо расширить профиль.

## Подозрительно длинные карточки
de-erman-bgb:rn:1, de-erman-bgb:rn:12/89, de-erman-bgb:rn:12/90, de-erman-bgb:rn:12/166, de-erman-bgb:rn:12/277, de-erman-bgb:rn:199/18, de-erman-bgb:rn:227/7, de-erman-bgb:rn:242/127, de-erman-bgb:rn:254/37, de-erman-bgb:rn:305c/14, de-erman-bgb:rn:311c/16, de-erman-bgb:rn:312d/11, de-erman-bgb:rn:315/19, de-erman-bgb:rn:326/49, de-erman-bgb:rn:387/19
Длинная карточка почти всегда означает, что следующий номер не распознан и две единицы слиплись.

## Подозрительно короткие карточки
de-erman-bgb:rn:1476, de-erman-bgb:rn:2373, de-erman-bgb:rn:2381, de-erman-bgb:rn:2550, de-erman-bgb:rn:2683, de-erman-bgb:rn:2704, de-erman-bgb:rn:2715, de-erman-bgb:rn:3190, de-erman-bgb:rn:3328, de-erman-bgb:rn:4619, de-erman-bgb:rn:4790, de-erman-bgb:rn:5164, de-erman-bgb:rn:5246, de-erman-bgb:rn:5326, de-erman-bgb:rn:5369

## Страницы, не попавшие ни в одну карточку
64, 66, 67, 69, 81, 200, 217, 245, 262, 856, 2708, 4320, 4927, 4928, 5252, 5253, 5256, 5259, 5260, 5261, 5262, 5263, 5264, 5265, 5421, 5435, 5436, 5460, 5464, 5467, 5468, 5474, 5554, 5555, 6297, 6298, 6300, 6304, 6310, 6312

## Спорные номера


Ни один номер не был изменён молча: здесь весь след. Ошибка в цифре адреса тяжелее обычной опечатки, потому что ломает саму ссылку.

## Случайные карточки для глазной проверки

### de-erman-bgb:rn:611a/317
*Erman/Edenfeld/Bieder, BGB, 17. Aufl. 2023, § 611a Rn 317*
Адрес: § 611a Rn 317 | иерархия: § 611a → Titel 8. Dienstvertrag und ähnliche Verträge (§§ 611–630h) | стр. файла 2882–2882, книги 2824–2824
Нормы: — | отсылки: —

Weitere Voraussetzung ist ein Widerspruch des Betriebs- bzw Personalrats gegen die Kündigung, § 102 V
BetrVG. Bei offensichtlicher Unbegründetheit des Widerspruchs (§ 102 V 2 Nr 3 BetrVG) steht dem ArbGeb eine
Einwendung zu (Rn 321).


### de-erman-bgb:rn:1843/2
*Erman/Schulte-Bunert, BGB, 17. Aufl. 2023, § 1843 Rn 2*
Адрес: § 1843 Rn 2 | иерархия: § 1843 → Abschnitt 3. Vormundschaft, Pflegschaft für Minderjährige, rechtliche Betreuung, sonstige Pflegschaft (§§ 1773–1921) | стр. файла 6219–6219, книги 6161–6161
Нормы: — | отсылки: —

2. Depotfähige Wertpapiere, Abs I. a) Verwahrt werden müssen alle Wertpapiere des Betreuten iSd § 1 I, II
DepotG. Wertpapiere sind nach § 1 I 1 DepotG Aktien, Kuxe, Zwischenscheine, Zins-, Gewinnanteil- und Erneuerungsscheine, auf den Inhaber lautende oder durch Indossament übertragbare Schuldverschreibungen, ferner andere Wertpapiere, wenn diese vertretbar sind (§ 91), mit Ausnahme von Banknoten und Papiergeld. Ferner zählen dazu nach § 1 I 2 DepotG auch Namensschuldverschreibungen, soweit sie auf den Namen einer
Wertpapiersammelbank ausgestellt wurden und es kann sich nach § 1 I 3 DepotG auch um elektronisch begebene Wertpapiere handeln (vgl zu den verschiedenen Arten von Wertpapieren Vor § 793 Rn 2f). b) Einzelne Wertpapiere: Eine Aktie stellt einen Anteil an einer AG oder KGaA dar, vgl auch § 1 II AktG. Kuxe sind ideelle Anteile an einem Bergwerk, welches im Rahmen einer bergrechtl G…


### de-erman-bgb:rn:2/10
*Erman/Norpoth/Sasse, BGB, 17. Aufl. 2023, § 2 Rn 10*
Адрес: § 2 Rn 10 | иерархия: § 2 → Gesetz über den Versorgungsausgleich (Versorgungsausgleichsgesetz – VersAusglG) | стр. файла 5404–5404, книги 5346–5346
Нормы: — | отсылки: —

1. Kapitalzahlung. Einmalige Leistungen bzw auf einzelne Kapitalleistungen (Ratenzahlungen) gerichtete
Versorgungen sind danach grds nicht in den VersA einzubeziehen. Davon macht das neue Recht jedoch Ausnahmen für Anrechte nach dem BetrAVG und nach dem AltZertG; diese unterfallen auch dann dem Regelungsbereich des VersAusglG, wenn sie auf eine Kapitalzahlung gerichtet sind (Bsp: BGH FamRZ 2014, 1613). Sogar
Bausparverträge können dadurch erfasst sein, wenn sie nach dem AltZertG zur Bildung von Wohneigentum abgeschlossen sind („Wohnriester“: vgl Brandenburg FamRZ 2013, 1039 Rn 63ff; näher Götsche FamRB 2014, 65,
66 mwN; zu Ausnahmen s Köln FamRZ 2022, 865). Die teilw Einbeziehung von auf Kapitalzahlung gerichteten
Anrechten entzieht diese dem Zugewinnausgleich und schützt den Inhaber vor einer Ausgleichspflicht mit
Rechtskraft der Entscheidung zum Zugewinnausgleich, die er aus verfügbare…


### de-erman-bgb:rn:1487/3
*Erman/Heinemann, BGB, 17. Aufl. 2023, § 1487 Rn 3*
Адрес: § 1487 Rn 3 | иерархия: § 1487 → Abschnitt 1. Bürgerliche Ehe (§§ 1297–1588) | стр. файла 5234–5234, книги 5176–5176
Нормы: — | отсылки: —

3. Minderjährige Abkömmlinge. Ist der überlebende Ehegatte gesetzl Vertreter der Kinder, so kann er für
diese trotz § 181 seine Einwilligung dem Vertragsgegner erklären (RGZ 76, 93; BayObLG DNotZ 1952, 163; aM
Staudinger/Thiele Rn 14; NK/Völker Rn 5, die vor allem wegen der Interessenkollision die Bestellung eines Pflegers verlangen). Der überlebende Ehegatte muss aber in den Fällen der §§ 1643, 1821 die Genehmigung des
FamG einholen (MüKo/Münch Rn 7).


### de-erman-bgb:rn:856/1
*Erman/Elzer, BGB, 17. Aufl. 2023, § 856 Rn 1*
Адрес: § 856 Rn 1 | иерархия: § 856 → Abschnitt 1. Besitz (§§ 854–872) | стр. файла 4328–4328, книги 4270–4270
Нормы: — | отсылки: —

I. Zweck und Anwendungsbereich. § 856 bestimmt, wann der unmittelbare Besitz endet. Ob es sich um Allein- oder Mitbesitz (uU jew als Teilbesitz) an beweglichen Sachen oder Grundstücken handelt, ist unerheblich.
Die Besitzaufgabe ist ein Element der Aufgabe des Eigentums an beweglichen Sachen (§ 959 Rn 5).


### de-erman-bgb:rn:453/7
*Erman/Grunewald, BGB, 17. Aufl. 2023, § 453 Rn 7*
Адрес: § 453 Rn 7 | иерархия: § 453 → Titel 1. Kauf, Tausch (§§ 433–480) | стр. файла 2167–2167, книги 2109–2109
Нормы: — | отсылки: —

Sollte das verkaufte Recht nicht in dem geschuldeten Umfang bestehen (Forderung besteht nicht in der vereinbarten Höhe, ist später fällig, wird geringer verzinst), ist auch dies ein Fall der Nichterfüllung – eben der
Pflicht zur vollständigen Rechtsverschaffung (aA NK/Büdenbender Rn 11: Rechtsmangel, aA auch Ackermann,
Einkaufsbedingungen beim Forderungskauf, 2020, 44ff; PWW/Wagner Rn 8: Sachmangel, aber es wird an keine
Sachbeschaffenheit angeknüpft, s Rn 13).


### de-erman-bgb:rn:675/93
*Erman/Berger, BGB, 17. Aufl. 2023, § 675 Rn 93*
Адрес: § 675 Rn 93 | иерархия: § 675 → Titel 12. Auftrag, Geschäftsbesorgungsvertrag und Zahlungsdienste (§§ 662–676c) | стр. файла 3477–3477, книги 3419–3419
Нормы: — | отсылки: —

c) Haftung. Auch für die Haftung bei Pflichtverletzungen gilt das zum Anwaltsvertrag (s Rn 72ff) und zum
Steuerberatungsvertrag (Rn 89) Gesagte entspr. Zum Mitverschulden des Geschäftsführers der geprüften Gesellschaft gem § 254 I s BGHZ 183, 323. S zur gesetzl Haftung des Abschlussprüfers nach § 323 I 3, 4 (Verletzung
der Pflicht zu gewissenhafter und unparteiischer Prüfung, der Verschwiegenheitspflicht und des Verbotes der
unbefugten Verwertung von Geschäfts- und Betriebsgeheimnissen aus Abs I S 1 und 2) und II (gesetzl Haftungshöchstbetrag!) HGB, MüKo-HGB/Ebke4 2020, § 323 Rn 20ff; Heymann/Herrmann, HGB3 2020, § 323 Rn 7ff;
Großkomm-HGB/Habersack/Schürnbrand5 2010, § 323 Rn 30ff; Poll DZWIR 1995, 95; Quick BB 1992, 1675;
Bärenz BB 2003, 1781. Der Abschlussprüfer ist für Fehler nach § 323 I 3 HGB nur der Gesellschaft und, wenn
ein verbundenes Unternehmen geschädigt worden ist, auch die…


### de-erman-bgb:rn:249/35
*Erman/Ebert, BGB, 17. Aufl. 2023, § 249 Rn 35*
Адрес: § 249 Rn 35 | иерархия: § 249 → Titel 1. Verpflichtung zur Leistung (§§ 241–292) | стр. файла 972–973, книги 914–915
Нормы: — | отсылки: —

Zu der anderen, sehr viel häufigeren Form der abstrakten Schadensberechnung kommt es in den Fällen, in denen eine gesetzl Vermutung für einen Gewinnentgang besteht, also in den allg zB durch § 252 S 2 erfassten Fallgruppen (BGHZ 126, 305f; LAG München 25.6.2020 – 3 Sa 620/19). Soweit diese Art der Berechnung in Betracht kommt, bleibt dem Gläubiger der Weg der konkreten Schadensberechnung als Alternative offen. Signifikant für die abstrakte Schadensberechnung sind – soweit es um die Folgen von Vertragsverletzungen geht – die
typischen Geschäfte des Handelsverkehrs (Handelskauf) mit marktgängigen Waren (Serienfabrikate, Massengüter) oder Dienstleistungen (MüKo/Emmerich Vor § 281 Rn 42). Hiervon auszunehmen sind Handelskäufe,
die nicht ersatzfähige bzw nachlieferbare Gegenstände betreffen, etwa originale Kunstwerke (zur Wertermittlung
bei Kunstwerken: Brandenburg NZM 2014, 167). Hier scheid…


### de-erman-bgb:rn:993/41
*Erman/Ebbing, BGB, 17. Aufl. 2023, § 993 Rn 41*
Адрес: § 993 Rn 41 | иерархия: § 993 → Abschnitt 3. Eigentum (§§ 903–1017) | стр. файла 4588–4588, книги 4530–4530
Нормы: — | отсылки: —

Die Anwendbarkeit der §§ 812ff im Eigentümer-Besitzer-Verhältnis ist im Einz umstr (zum Streitstand MüKo/
Raff § 994 Rn 66 und § 996 Rn 13ff; Staudinger/Thole Vor §§ 994–1003 Rn 83ff). Man wird von Folgendem ausgehen können:


### de-erman-bgb:rn:809/7
*Erman/Wilhelmi, BGB, 17. Aufl. 2023, § 809 Rn 7*
Адрес: § 809 Rn 7 | иерархия: § 809 → Titel 25. Vorlegung von Sachen (§§ 809–811) | стр. файла 4087–4087, книги 4029–4029
Нормы: — | отсылки: —

7. Verjährung. Der Anspruch auf Vorlegung verjährt nicht, ist jedoch nach Verjährung des Hauptanspruchs
nicht mehr begründet (Karlsruhe NJW-RR 2002, 951; Staudinger/Marburger Vor §§ 809ff Rn 4; aA MüKo/Habersack Rn 15; Grü/Sprau Rn 12).
§ 810 Einsicht in Urkunden
Wer ein rechtliches Interesse daran hat, eine in fremdem Besitz befindliche Urkunde einzusehen, kann von
dem Besitzer die Gestattung der Einsicht verlangen, wenn die Urkunde in seinem Interesse errichtet oder in
der Urkunde ein zwischen ihm und einem anderen bestehendes Rechtsverhältnis beurkundet ist oder wenn
die Urkunde Verhandlungen über ein Rechtsgeschäft enthält, die zwischen ihm und einem anderen oder
zwischen einem von beiden und einem gemeinschaftlichen Vermittler gepflogen worden sind.


## СТОП: выгружать нельзя

- Непрерывность нумерации 97.2% < 98%: пропущено номеров 1803. Паттерн местами не сработал, и эти куски книги в корпус не попали.
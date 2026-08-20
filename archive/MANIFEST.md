# Резервная выгрузка корпуса

Снята: 2026-08-20 17:02 UTC. Сервис: https://37-27-248-75.sslip.io.
Источников: 69, чанков: 89190.

Эмбеддинги СЮДА НЕ ВХОДЯТ — API их не отдаёт. Пересчитываются из
текста моделью `text-embedding-3-small` (весь корпус — меньше доллара).
Полный дамп базы вместе с векторами снимается на машине сервиса:
см. `docs/backup.md`.

СНОСКИ НЕ ВЫГРУЖЕНЫ: сервис не поддерживает `?with_footnotes=true`. Затронуто источников: 69.

| Чанков | Сносок | Размер | Юрисдикция | Источник | Файл |
|---|---|---|---|---|---|
| 8774 | 0 | 2894 КБ | AT | Insolvenzordnung | `at--insolvenzordnung--2b1ac524.jsonl.gz` |
| 6162 | 0 | 2539 КБ | AT | Kommentar zum ABGB Allgemeines bürgerliches Gesetzbuch, EheG, KSchG, V | `at--kommentar-zum-abgb-allgemeines-bürgerliches-gesetzbuch-eheg--199fa63c.jsonl.gz` |
| 4361 | 0 | 1614 КБ | UK | English Private Law | `uk--english-private-law--2542819d.jsonl.gz` |
| 4285 | 0 | 1457 КБ | AT | GmbHG. Gesetz über Gesellschaften mit beschränkter Haftung. Praxiskomm | `at--gmbhg-gesetz-über-gesellschaften-mit-beschränkter-haftung-pr--01337b21.jsonl.gz` |
| 4059 | 0 | 2256 КБ | AT | ZPO. Zivilprozessordnung. Kommentar | `at--zpo-zivilprozessordnung-kommentar--3d5f6cc8.jsonl.gz` |
| 3877 | 0 | 1819 КБ | UK | Chitty on Contracts. Volume 2: Specific Contracts | `uk--chitty-on-contracts-volume-2-specific-contracts--a3319b17.jsonl.gz` |
| 3800 | 0 | 1939 КБ | UK | Chitty on Contracts. Volume 1: General Principles | `uk--chitty-on-contracts-volume-1-general-principles--8494b9f8.jsonl.gz` |
| 2929 | 0 | 1219 КБ | UK | The Law of Real Property | `uk--the-law-of-real-property--d42a865b.jsonl.gz` |
| 2645 | 0 | 1287 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 859-887 (Allgemeines Vertragsrecht) | `at--abgb-on-klang-grosskommentar-859-887-allgemeines-vertragsrec--0a517995.jsonl.gz` |
| 2447 | 0 | 836 КБ | AT | Grundriss des bürgerlichen Rechts. Band II. Schuldrecht Allgemeiner Te | `at--grundriss-des-bürgerlichen-rechts-band-ii-schuldrecht-allgem--7bf6ab50.jsonl.gz` |
| 2396 | 0 | 978 КБ | UK | Goff & Jones. The Law of Unjust Enrichment | `uk--goff-jones-the-law-of-unjust-enrichment--1bf6771a.jsonl.gz` |
| 2231 | 0 | 1068 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1002-1044 (Bevollmächtigung und and | `at--abgb-on-klang-grosskommentar-1002-1044-bevollmächtigung-und--42d126d0.jsonl.gz` |
| 2131 | 0 | 1118 КБ | UK | Treitel: The Law of Contract | `uk--treitel-the-law-of-contract--fcf8cbe0.jsonl.gz` |
| 1989 | 0 | 922 КБ | UK | The Law of Personal Property | `uk--the-law-of-personal-property--bab3a454.jsonl.gz` |
| 1979 | 0 | 936 КБ | UK | Snell's Equity | `uk--snells-equity--a838bc38.jsonl.gz` |
| 1845 | 0 | 673 КБ | AT | Grundriss des bürgerlichen Rechts. Band I. Allgemeiner Teil, Sachenrec | `at--grundriss-des-bürgerlichen-rechts-band-i-allgemeiner-teil-sa--5574adbd.jsonl.gz` |
| 1806 | 0 | 1736 КБ | AT | Zivilrecht. Grundriss und Einfuerung in das Rechtsdenken. Teil 1 | `at--zivilrecht-grundriss-und-einfuerung-in-das-rechtsdenken-teil--66bf2223.jsonl.gz` |
| 1664 | 0 | 837 КБ | BE | Handboek Verbintenissenrecht | `be--handboek-verbintenissenrecht--92595633.jsonl.gz` |
| 1651 | 0 | 702 КБ | UK | A New Land Law | `uk--a-new-land-law--1f14b57a.jsonl.gz` |
| 1394 | 0 | 478 КБ | UK | Principles of the English Law of Obligations | `uk--principles-of-the-english-law-of-obligations--e20cf52f.jsonl.gz` |
| 1280 | 0 | 848 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 447-530 (Pfandrecht) | `at--abgb-on-klang-grosskommentar-447-530-pfandrecht--85cb6963.jsonl.gz` |
| 1237 | 0 | 1111 КБ | UK | Gower: Principles of Modern Company Law | `uk--gower-principles-of-modern-company-law--2a48ea1b.jsonl.gz` |
| 1225 | 0 | 609 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1175-1216e (GesbR) | `at--abgb-on-klang-grosskommentar-1175-1216e-gesbr--bcf932a3.jsonl.gz` |
| 1143 | 0 | 408 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1342-1374 (Bürgschaft, Pfandrecht) | `at--abgb-on-klang-grosskommentar-1342-1374-bürgschaft-pfandrecht--6a023cbc.jsonl.gz` |
| 1138 | 0 | 714 КБ | UK | Textbook on Land Law | `uk--textbook-on-land-law--09e3954b.jsonl.gz` |
| 1068 | 0 | 475 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1165-1174 (Werkvertrag, Verlagsvert | `at--abgb-on-klang-grosskommentar-1165-1174-werkvertrag-verlagsve--e0180a5d.jsonl.gz` |
| 1022 | 0 | 943 КБ | UK | Hanbury & Martin: Modern Equity | `uk--hanbury-martin-modern-equity--e06078f8.jsonl.gz` |
| 868 | 0 | 730 КБ | UK | The Principles of the Law of Restitution | `uk--the-principles-of-the-law-of-restitution--b809efa9.jsonl.gz` |
| 860 | 0 | 583 КБ | AT | Österreichisches Bankvertragsrecht, Band IX: Kreditsicherheiten, Teil  | `at--österreichisches-bankvertragsrecht-band-ix-kreditsicherheite--ef420057.jsonl.gz` |
| 846 | 0 | 327 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1151-1164a (Dienstvertrag) | `at--abgb-on-klang-grosskommentar-1151-1164a-dienstvertrag--7fd3556a.jsonl.gz` |
| 810 | 0 | 400 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 938-1001 (Schenkung, Verwahrung, Le | `at--abgb-on-klang-grosskommentar-938-1001-schenkung-verwahrung-l--5bf5bad1.jsonl.gz` |
| 734 | 0 | 459 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 897-916 (Vertragsrecht) | `at--abgb-on-klang-grosskommentar-897-916-vertragsrecht--885bae49.jsonl.gz` |
| 732 | 0 | 457 КБ | AT | Österreichisches Bankvertragsrecht, Band VII: Factoring, Leasing und F | `at--österreichisches-bankvertragsrecht-band-vii-factoring-leasin--cf87809c.jsonl.gz` |
| 687 | 0 | 273 КБ | AT | Bürgerliches Recht. Band IV: Sachenrecht | `at--bürgerliches-recht-band-iv-sachenrecht--cee6d949.jsonl.gz` |
| 680 | 0 | 426 КБ | AT | Österreichisches Bankvertragsrecht, Band II: Konto und Depot | `at--österreichisches-bankvertragsrecht-band-ii-konto-und-depot--55cf87c3.jsonl.gz` |
| 655 | 0 | 514 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1375-1410 (Anweisung, Vergleich und | `at--abgb-on-klang-grosskommentar-1375-1410-anweisung-vergleich-u--7d519a85.jsonl.gz` |
| 649 | 0 | 938 КБ | UK | Property Law: Cases and Materials | `uk--property-law-cases-and-materials--a71a9813.jsonl.gz` |
| 594 | 0 | 387 КБ | AT | Österreichisches Bankvertragsrecht, Band IV: Kreditgeschäft | `at--österreichisches-bankvertragsrecht-band-iv-kreditgeschäft--076b9520.jsonl.gz` |
| 585 | 0 | 447 КБ | AT | Österreichisches Bankvertragsrecht, Band VIII: Kreditsicherheiten, Tei | `at--österreichisches-bankvertragsrecht-band-viii-kreditsicherhei--4c03b507.jsonl.gz` |
| 568 | 0 | 386 КБ | AT | Grundbuchsrecht | `at--grundbuchsrecht--15d05cc4.jsonl.gz` |
| 513 | 0 | 446 КБ | UK | Principles of Tort Law | `uk--principles-of-tort-law--ad30fdbf.jsonl.gz` |
| 488 | 0 | 394 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 380-446 (Eigentum) | `at--abgb-on-klang-grosskommentar-380-446-eigentum--f2daa10e.jsonl.gz` |
| 486 | 0 | 233 КБ | AT | Bürgerliches Recht. Band III. Schuldrecht. Besonderer Teil | `at--bürgerliches-recht-band-iii-schuldrecht-besonderer-teil--0281ce69.jsonl.gz` |
| 485 | 0 | 626 КБ | UK | Street on Torts | `uk--street-on-torts--13241132.jsonl.gz` |
| 476 | 0 | 405 КБ | AT | Österreichisches Bankvertragsrecht, Band V: Akkreditiv und Garantie | `at--österreichisches-bankvertragsrecht-band-v-akkreditiv-und-gar--5106da31.jsonl.gz` |
| 464 | 0 | 188 КБ | AT | Schuldrecht. Allgemeiner Teil | `at--schuldrecht-allgemeiner-teil--c6417342.jsonl.gz` |
| 447 | 0 | 365 КБ | AT | Allgemeiner Teil des Bürgerlichen Rechts | `at--allgemeiner-teil-des-bürgerlichen-rechts--3e796acb.jsonl.gz` |
| 424 | 0 | 164 КБ | AT | Bürgerliches Recht Band VI. Erbrecht | `at--bürgerliches-recht-band-vi-erbrecht--33d97cda.jsonl.gz` |
| 410 | 0 | 521 КБ | UK | Contract Law | `uk--contract-law--52915769.jsonl.gz` |
| 392 | 0 | 261 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1431-1437 (Bereicherungsrecht) | `at--abgb-on-klang-grosskommentar-1431-1437-bereicherungsrecht--41b39a63.jsonl.gz` |
| 389 | 0 | 479 КБ | UK | The Law of Tracing | `uk--the-law-of-tracing--50c0ebda.jsonl.gz` |
| 380 | 0 | 456 КБ | UK | Modern Land Law | `uk--modern-land-law--a0587e0c.jsonl.gz` |
| 375 | 0 | 165 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1411-1430 (Aufhebung der Rechte) | `at--abgb-on-klang-grosskommentar-1411-1430-aufhebung-der-rechte--05b2c6ff.jsonl.gz` |
| 358 | 0 | 244 КБ | AT | Österreichisches Bankvertragsrecht, Band III: Zahlungsverkehr | `at--österreichisches-bankvertragsrecht-band-iii-zahlungsverkehr--08576050.jsonl.gz` |
| 342 | 0 | 141 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 905-907b (Erfüllung von Geldschulde | `at--abgb-on-klang-grosskommentar-905-907b-erfüllung-von-geldschu--15b9327e.jsonl.gz` |
| 318 | 0 | 530 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 1328-1329 (Schadenersatz) | `at--abgb-on-klang-grosskommentar-1328-1329-schadenersatz--b5fcae4f.jsonl.gz` |
| 317 | 0 | 219 КБ | UK | A Restatement of the English Law of Contract | `uk--a-restatement-of-the-english-law-of-contract--1540ae2f.jsonl.gz` |
| 271 | 0 | 202 КБ | AT | ABGB-ON — Klang Grosskommentar, §§ 888-896 (Gemeinschaft von Gläubiger | `at--abgb-on-klang-grosskommentar-888-896-gemeinschaft-von-gläubi--e4d055cc.jsonl.gz` |
| 270 | 0 | 234 КБ | BE | Proposition de loi portant le livre 5 «Les obligations» du Code civil  | `be--proposition-de-loi-portant-le-livre-5-les-obligations-du-cod--31c95dfd.jsonl.gz` |
| 267 | 0 | 177 КБ | AT | Bürgerliches Recht. Band VII: Internationales Privatrecht | `at--bürgerliches-recht-band-vii-internationales-privatrecht--6396ae41.jsonl.gz` |
| 223 | 0 | 144 КБ | AT | Bürgerliches Recht. Band V: Familienrecht | `at--bürgerliches-recht-band-v-familienrecht--315b5fe2.jsonl.gz` |
| 221 | 0 | 103 КБ | UK | Law Express: Land Law | `uk--law-express-land-law--bec9df23.jsonl.gz` |
| 220 | 0 | 229 КБ | UK | An Introduction to Tort Law | `uk--an-introduction-to-tort-law--6660d71c.jsonl.gz` |
| 202 | 0 | 508 КБ | UK | Corporate Insolvency Law: Perspectives and Principles | `uk--corporate-insolvency-law-perspectives-and-principles--bef4bcc9.jsonl.gz` |
| 198 | 0 | 192 КБ | UK | The Law of Property | `uk--the-law-of-property--22c651ec.jsonl.gz` |
| 186 | 0 | 270 КБ | BE | Proposition de loi portant le livre 3 «Les biens» du Code civil — Déve | `be--proposition-de-loi-portant-le-livre-3-les-biens-du-code-civi--a9035768.jsonl.gz` |
| 164 | 0 | 223 КБ | UK | Contract Law | `uk--contract-law--62a73b60.jsonl.gz` |
| 55 | 0 | 28 КБ | BE | Proposition de loi portant le titre 1er «Les sûretés personnelles» du  | `be--proposition-de-loi-portant-le-titre-1er-les-sûretés-personne--45bc3bf6.jsonl.gz` |
| 43 | 0 | 131 КБ | BE | Proposition de loi portant le livre 6 «La responsabilité extracontract | `be--proposition-de-loi-portant-le-livre-6-la-responsabilité-extr--2178cfe9.jsonl.gz` |

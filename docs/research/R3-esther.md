# R3. Esther: what the WEB-C text contains and how it maps to the Nova Vulgata

Research item R3 (spec: `docs/corpus-cleanup/P0-checks-identity-research.md`, "### R3."). Blocks 1.4a.
Done 4 Oct 2026. Research only: no production query was made. The live Esther references are the ones the spec records.

## Summary

- The vendored file holds all six Greek additions, A to F. WEB-C's introduction says five because it treats C and D as one. D, which the spec marked unverified, is WEB-C 5:1-2. It has no brackets.
- Only C (WEB-C 4:18-47) and F (10:4-14) are missing from the live corpus. That is 41 verses, as the plan says. A, B, D and E sit inside verses the KJV pericopes already cover (1:1, 3:13, 5:1-2, 8:13), so they are live today.
- The chapter 4 and chapter 9 gaps are explained. WEB-C has no 4:6, 9:5 or 9:30. Those are Hebrew-text verses that its Greek source lacks. The Nova Vulgata has all three.
- The Nova Vulgata keeps the Hebrew chapter and verse numbers and inserts the Greek material as lettered verses after the verse it follows (1:1a-k, 3:13a-h, 3:15a-i, 4:8a, 4:17a-kk, 5:2a-p, 8:12a-cc, 9:19a, 10:3a-k; 3:15a-i and 9:19a are Old Latin with no Greek counterpart). Its Praenotanda says so. They also say the Latin of the additions follows the Vetus Latina (the Old Latin version), except the two royal decrees. So the Nova Vulgata's additions are a different text form from the Greek that WEB-C translates. Some WEB-C verses have no Nova Vulgata counterpart, and some Nova Vulgata verses have no WEB-C counterpart.
- Church documents use two schemes, and neither is the Nova Vulgata's. The Catechism ("Esth 4:17b") and the Italian Lectionary ("Est 4,17k-u") fit the Septuagint's lettering of the Greek text (Mordecai's prayer 4:17a-i, Esther's 4:17k-z), which labels the same Greek that WEB-C translates. The English Lectionary (USCCB and Vatican News) cites "Esther C:12, 14-16, 23-25", the NAB's letter chapters. See section 5.
- **Recommendation:** keep WEB-C chapter and verse numbers in references, anchors and `{{v:N}}` markers. Name each addition by its letter in the pericope title (for example "Addition C: Esther's prayer"). Record the Nova Vulgata range in metadata only at the level of whole additions, where the mapping is exact. Restoring C and F creates new units only, so no existing anchor changes its text and no D1 redirect is needed.

## 1. Verse inventory of `43-ESGeng-web-c.usfm` (script output)

Source: `datapipeline/sources/bible/eng-web-c_usfm/43-ESGeng-web-c.usfm` in the main checkout, 287 lines (no final newline), sha256 `4f4e3eb2af162a805419b22c8a9f1239b7a537ed02045142e5c427aff20881fa`. Script: `docs/research/R3_esther_inventory.py`. It is read-only and reads the gitignored sources under the checkout's own `datapipeline/sources/`, so run it from a checkout that has them vendored. Command and complete output:

```
$ python3 docs/research/R3_esther_inventory.py
== Per-chapter verse markers ==
ch  1: 22 markers, lines 13-39, highest verse 22, numbers covered 22
ch  2: 23 markers, lines 42-69, highest verse 23, numbers covered 23
ch  3: 15 markers, lines 72-89, highest verse 15, numbers covered 15
ch  4: 46 markers, lines 92-142, highest verse 47, numbers covered 46
        numbers never marked: [6]
ch  5: 14 markers, lines 145-166, highest verse 14, numbers covered 14
ch  6: 14 markers, lines 170-191, highest verse 14, numbers covered 14
ch  7: 10 markers, lines 194-209, highest verse 10, numbers covered 10
ch  8: 17 markers, lines 212-231, highest verse 17, numbers covered 17
ch  9: 30 markers, lines 234-270, highest verse 32, numbers covered 30
        numbers never marked: [5, 30]
ch 10: 14 markers, lines 273-287, highest verse 14, numbers covered 14
total markers: 205

== Marker -> USFM line (all verses) ==
ch 1: 1@13 2@17 3@18 4@19 5@20 6@21 7@22 8@23 9@25 10@26 11@27 12@28 13@29 14@31 15@32 16@33 17@34 18@35 19@36 20@37 21@38 22@39
ch 2: 1@42 2@43 3@44 4@45 5@48 6@49 7@50 8@51 9@52 10@53 11@54 12@56 13@57 14@58 15@59 16@60 17@61 18@62 19@64 20@65 21@67 22@68 23@69
ch 3: 1@72 2@73 3@74 4@75 5@76 6@77 7@79 8@80 9@81 10@83 11@84 12@85 13@86 14@88 15@89
ch 4: 1@92 2@93 3@94 4@95 5@96 7@97 8@98 9@100 10@101 11@102 12@104 13@105 14@106 15@108 16@109 17@111 18@112 19@113 20@114 21@115 22@116 23@117 24@118 25@119 26@120 27@121 28@123 29@124 30@125 31@126 32@127 33@128 34@129 35@130 36@131 37@132 38@133 39@134 40@135 41@136 42@137 43@138 44@139 45@140 46@141 47@142
ch 5: 1@145 2@147 3@150 4@152 5@154 6@155 7@157 8@158 9@160 10@161 11@162 12@163 13@164 14@166
ch 6: 1@170 2@171 3@172 4@175 5@176 6@179 7@181 8@182 9@183 10@185 11@187 12@188 13@190 14@191
ch 7: 1@194 2@195 3@197 4@198 5@200 6@202 7@204 8@205 9@207 10@209
ch 8: 1@212 2@213 3@214 4@215 5@216 6@217 7@219 8@220 9@221 10@222 11@223 12@224 13@225 14@227 15@229 16@230 17@231
ch 9: 1@234 2@235 3@236 4@237 6@238 7@239 8@240 9@241 10@242 11@243 12@245 13@247 14@249 15@250 16@252 17@253 18@255 19@256 20@258 21@259 22@260 23@261 24@262 25@263 26@264 27@265 28@266 29@268 31@269 32@270
ch 10: 1@273 2@274 3@276 4@277 5@278 6@279 7@280 8@281 9@282 10@283 11@284 12@285 13@286 14@287

== Bracketed spans (Greek additions as WEB-C marks them) ==
opens 1:1 (line 13)  closes 1:1 (line 15)
opens 3:13 (line 86)  closes 3:13 (line 87)
opens 4:18 (line 112)  closes 4:47 (line 142)
opens 8:13 (line 226)  closes 8:13 (line 226)
opens 10:4 (line 277)  closes 10:14 (line 287)

== Verse lengths over 1,500 characters (plain text) ==
1:1  2104 chars
3:13  2086 chars
8:13  4183 chars

== WEB-C verses outside every KJV Esther pericope (dropped today) ==
KJV Esther pericopes: 24
4:18-47  (30 verses, USFM lines 112-142)
10:4-14  (11 verses, USFM lines 277-287)
total dropped: 41
```

What the output shows:

- 205 verse markers in 10 chapters: 22, 23, 15, 46, 14, 14, 10, 17, 30, 14. This matches the spec. No marker carries a range (such as `\v 7-8`), and no number is used twice.
- Three verse numbers are never marked: 4:6 (between line 96, `\v 5`, and line 97, `\v 7`), 9:5 (between lines 237 and 238) and 9:30 (between lines 268 and 269). No verses are combined. The numbers are simply absent. The Nova Vulgata has all three (4:6 "Egressusque Athach ivit ad Mardochaeum…", 9:5 "Itaque percusserunt Iudaei omnes inimicos suos…", 9:30 "Et miserunt ad omnes Iudaeos…"), so they are Hebrew-text verses that WEB-C's Greek text does not carry. This is the explanation for the "unexplained" chapter 9 gap.
- WEB-C uses square brackets to mark additions. There are five bracketed spans: A, B, C, E and F. D is not bracketed.
- Three verses are very long because a whole addition is folded into one verse: 1:1 (A), 3:13 (B) and 8:13 (E). The introduction (line 10) says "1:1, 5:1, and 8:12". 5:1 holds D but is under 1,500 characters. E is in 8:13, not 8:12.

The current adapter, `build_documents` in this worktree, run on Esther alone with the pericope path pointed at the main checkout. The same 26 passages are live:

```
Esther 26 passages
  esther/1/1     Esther 1:1–8     3416 chars
  esther/1/9     Esther 1:9–12    544 chars
  esther/1/13    Esther 1:13–22   1603 chars
  esther/2/1     Esther 2:1–4     696 chars
  esther/2/5     Esther 2:5–16    2143 chars
  esther/2/17    Esther 2:17–20   556 chars
  esther/2/21    Esther 2:21–23   487 chars
  esther/3/1     Esther 3:1–2     260 chars
  esther/3/3-1   Esther 3:3–15    2951 chars
  esther/3/3-2   Esther 3:3–15    1007 chars
  esther/4/1     Esther 4:1–3     561 chars
  esther/4/4     Esther 4:4–17    2179 chars
  esther/5/1     Esther 5:1–4     1923 chars
  esther/5/5     Esther 5:5–8     496 chars
  esther/5/9     Esther 5:9–14    859 chars
  esther/6/1     Esther 6:1–11    1818 chars
  esther/6/12    Esther 6:12–14   535 chars
  esther/7/1     Esther 7:1–6     802 chars
  esther/7/7     Esther 7:7–10    736 chars
  esther/8/1-1   Esther 8:1–14    3805 chars
  esther/8/1-2   Esther 8:1–14    2550 chars
  esther/8/15    Esther 8:15–17   416 chars
  esther/9/1     Esther 9:1–10    796 chars
  esther/9/11    Esther 9:11–17   992 chars
  esther/9/18    Esther 9:18–32   2276 chars
  esther/10/1    Esther 10:1–3    369 chars
```

## 2. Additions A to F: WEB-C range and Nova Vulgata range

The Nova Vulgata page is [Liber Esther](https://www.vatican.va/archive/bible/nova_vulgata/documents/nova-vulgata_vt_esther_lt.html), saved with curl and parsed by the same script. Output:

```
$ curl -sL -o nova-vulgata_vt_esther_lt.html https://www.vatican.va/archive/bible/nova_vulgata/documents/nova-vulgata_vt_esther_lt.html
$ python3 docs/research/R3_esther_inventory.py --nv nova-vulgata_vt_esther_lt.html
== Nova Vulgata Esther verse labels (vatican.va) ==
ch  1: 32 labels, plain verses 1-22, lettered 10
        1a 1b 1c 1d 1e 1f 1g 1h 1i 1k 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22
ch  2: 23 labels, plain verses 1-23, lettered 0
        1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23
ch  3: 32 labels, plain verses 1-15, lettered 17
        1 2 3 4 5 6 7 8 9 10 11 12 13 13a 13b 13c 13d 13e 13f 13g 13h 14 15 15a 15b 15c 15d 15e 15f 15g 15h 15i
ch  4: 52 labels, plain verses 1-17, lettered 35
        1 2 3 4 5 6 7 8 8a 9 10 11 12 13 14 15 16 17 17a 17b 17c 17d 17e 17f 17g 17h 17i 17k 17l 17m 17n 17o 17p 17q 17r 17s 17t 17u 17v 17x 17y 17z 17aa 17bb 17cc 17dd 17ee 17ff 17gg 17hh 17ii 17kk
ch  5: 29 labels, plain verses 1-14, lettered 15
        1 2 2a 2b 2c 2d 2e 2f 2g 2h 2i 2k 2l 2m 2n 2o 2p 3 4 5 6 7 8 9 10 11 12 13 14
ch  6: 14 labels, plain verses 1-14, lettered 0
        1 2 3 4 5 6 7 8 9 10 11 12 13 14
ch  7: 10 labels, plain verses 1-10, lettered 0
        1 2 3 4 5 6 7 8 9 10
ch  8: 44 labels, plain verses 1-17, lettered 27
        1 2 3 4 5 6 7 8 9 10 11 12 12a 12b 12c 12d 12e 12f 12g 12h 12i 12k 12l 12m 12n 12o 12p 12q 12r 12s 12t 12u 12v 12x 12y 12z 12aa 12bb 12cc 13 14 15 16 17
ch  9: 33 labels, plain verses 1-32, lettered 1
        1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 19a 20 21 22 23 24 25 26 27 28 29 30 31 32
ch 10: 13 labels, plain verses 1-3, lettered 10
        1 2 3 3a 3b 3c 3d 3e 3f 3g 3h 3i 3k
total labels: 282
```

The Nova Vulgata letters skip j and w (1:1i is followed by 1:1k; 4:17v by 4:17x). After z come aa, bb and so on. 3:13h, 4:8a and 9:19a are printed inline on the page, after the preceding verse, not on their own lines.

The NAB letter-chapter numbering is included because the English Lectionary uses it. Source: the NAB introduction to Esther on vatican.va ([ENG0839/_PD6.HTM](https://www.vatican.va/archive/ENG0839/_PD6.HTM)). It gives A 1-17, B 1-7, C 1-30, D 1-16, E 1-24, F 1-11, and the Clementine Vulgate equivalents (chapters 10:4 to 16:24).

| Addition | Content | WEB-C (USFM lines) | Nova Vulgata | NAB | Live today? |
|---|---|---|---|---|---|
| A | Mordecai's dream; the eunuchs' plot | Inside 1:1, bracketed, lines 13-15. The dream is lines 13-14, the plot line 15. Hebrew 1:1 follows on line 16. | 1:1a-1k = the dream only. **The plot (Greek A 12-17) is not in the Nova Vulgata.** | A 1-17 | Yes, in `esther/1/1` |
| B | Artaxerxes' first decree | Inside 3:13 after the Hebrew verse, bracketed, lines 86-87 | 3:13a-3:13h (the Praenotanda say 3:13a-g; the page also prints an h) | B 1-7 | Yes, in `esther/3/3-1`/`-2` |
| (B) | Mordecai's "Remember the days of your humble condition" | End of 4:8, not bracketed, line 98 | 4:8a | Counted as B 8-9 | Yes, in `esther/4/4` |
| C | Prayers of Mordecai and Esther | 4:18-4:47, bracketed, lines 112-142. 4:N = C (N-17), so 4:18 = C 1 and 4:47 = C 30. Mordecai: 4:18-28. Esther: 4:29-47. | 4:17a-4:17kk (34 labels). Mordecai: 17a-17m. Esther: 17n-17kk. Not verse-for-verse; see section 3. | C 1-30 | **No** (30 verses) |
| D | Esther before the king | 5:1-2, not bracketed, lines 145-149. The footnote at 5:1 says "From the first verse to the third, the Greek widely differs from the Hebrew". The Greek replaces Hebrew 5:1-2. | 5:2a-5:2p, after the Hebrew 5:1-2, which the Nova Vulgata keeps | D 1-16 | Yes, in `esther/5/1` |
| E | Artaxerxes' second decree | Inside 8:13, bracketed, line 226. It is preceded by a lead-in (line 225) and followed by a repeat of the 8:13 sentence (end of line 226). | 8:12d-8:12cc (E 1-24, 24 labels). 8:12a-c is a Latin lead-in that restates 8:11-12 ("Quomodo praecepit…", "Hoc est exemplar epistulae"). | E 1-24 | Yes, in `esther/8/1-1`/`-2` |
| F | Mordecai's dream interpreted; colophon | 10:4-10:14, bracketed, lines 277-287. 10:4-13 = F 1-10; 10:14 = the colophon (F 11). | 10:3a-10:3k = F 1-10, one to one: 10:4↔3a, 10:5↔3b, 10:6↔3c, 10:7↔3d, 10:8↔3e, 10:9↔3f, 10:10↔3g, 10:11↔3h, 10:12↔3i, 10:13↔3k. **The colophon (10:14) is not in the Nova Vulgata text.** | F 1-11 | **No** (11 verses) |

WEB-C 10:4-13 happens to match the Clementine Vulgate's 10:4-13, per the NAB table on vatican.va. WEB-C 4:18-47 matches no Church numbering.

## 3. Text in one but not the other, and duplication

The Praenotanda of the Nova Vulgata on vatican.va ([nova-vulgata_praenotanda_lt.html](https://www.vatican.va/archive/bible/nova_vulgata/documents/nova-vulgata_praenotanda_lt.html), the paragraph on "Liber ESTHER") say that the Church reads Esther in two canonical forms. The Greek is a reworking, not a simple version. The Nova Vulgata inserts the Greek additions "quae sunt maioris momenti" (those of greater weight) into the version of the Hebrew, numbered with letters after the verse numbers. Their translation "supponit textum versionis Veteris Latinae", that is, it follows the Old Latin text, except for the two royal decrees (3:13a-g, 8:12a-cc). That explains the differences below. The Nova Vulgata additions are not a Latin rendering of the Greek text WEB-C translates.

**Greek text in WEB-C with no Nova Vulgata counterpart**

- A 12-17, the eunuchs' plot (1:1, line 15).
- In C, by content (an alignment made by reading the two texts; no Church source maps them verse by verse): WEB-C 4:34-38 (C 17-21: "we have sinned … we honored their gods … the praises of vanities") has no counterpart. 4:33 (C 16, "you took Israel out of all the nations") is replaced in the Nova Vulgata by a different litany, 4:17s-aa ("Ego audivi ex libris maiorum meorum…": Noah, Abraham, Jonah, the three youths, Daniel, Hezekiah, Hannah). 4:39 survives only as its last clause (4:17ii), and 4:47 (C 30) has no clear counterpart. The Nova Vulgata also reorders Esther's prayer: WEB-C 4:41 and 4:43-46 appear in the order 4:17gg, cc, ff, dd, ee.
- The colophon, 10:14.
- Hebrew-portion verses also differ, because WEB-C translates the Greek throughout. Examples: WEB-C 9:29 "daughter of Aminadab" (line 268) against Nova Vulgata 9:29 "filia Abihail"; the Greek forms of the names of Haman's sons at 9:7-10 (lines 239-242).

**Nova Vulgata text with no WEB-C counterpart**

- Hebrew verses 4:6, 9:5 and 9:30, and the Hebrew form of 5:1-2. WEB-C has only the Greek D in that place.
- Old Latin material not in the Greek:
  - 3:15a-i, a lament and prayer of the Jews after the decree;
  - 4:17a, Mordecai tears his clothes with the elders "a mane usque ad vesperam";
  - 4:17p, Esther falls to the ground with her maids from morning to evening;
  - the 4:17s-aa litany;
  - the "Appare, Domine; manifestare, Domine" refrains at 4:17h and 4:17kk;
  - 9:19a, which echoes the Greek 9:3-4 (WEB-C lines 236-237).
- 8:12a-c, the Latin lead-in to E. It restates 8:11-13 and has only loose WEB-C counterparts: 12c "Hoc est exemplar epistulae" matches WEB-C 8:13's "The following is a copy of the letter" (line 225), and 12a-b restate WEB-C 8:11-12.

**Duplication**

- Hebrew-only Esther is not duplicated across books. The vendored WEB-C directory has one Esther file (`ESG`, Greek, mapped to "Esther" at `ingest/bible.py:76-78`) and no Hebrew `EST` file.
- Inside the Greek book there are two doublets:
  - A 12-17 (line 15, the eunuchs' plot) retells Hebrew 2:21-23 (lines 67-69). Both are in WEB-C and both are live, in `esther/1/1` and `esther/2/21`. This is in the Greek book itself, not an artefact of WEB-C. The Nova Vulgata avoids it by omitting A 12-17.
  - 8:13 carries its own sentence twice: once before E as "Let the copies be posted…" (line 225), and again after the bracket (end of line 226).

These are faithful to the source text and are not defects for 1.4a to remove.

## 4. Live Esther verses missing

The script's last section repeats the inclusive range test of `collect_pericope_verses` against the 24 KJV Esther pericopes. The verses dropped are 4:18-47 (30 verses, lines 112-142) and 10:4-14 (11 verses, lines 277-287), 41 in total. The adapter run above reproduces the live references the spec lists ("Esther 4:4–17", "Esther 10:1–3" and so on, 26 passages). The plan's "Esther 4:18-47 and 10:4-14" is **confirmed**. These are all of C and all of F (including F's colophon). A, B, D and E are not missing.

## 5. How Church documents cite the additions

1. **Catechism 269**, note 107: "Wis 11:21; cf. Esth 4:17b; Prov 21:1; Tob 13:2." It is cited for God's power that none can withstand ([vatican.va, CCC Part One, __P18.HTM](https://www.vatican.va/archive/ENG0015/__P18.HTM); concordance [ENG0015/3/SL.HTM](https://www.vatican.va/archive/ENG0015/3/SL.HTM)). The matching text is Mordecai's "there is no one who can oppose you" (WEB-C 4:19 = C 2). In the Nova Vulgata that is 4:17c ("non est qui possit tuae resistere voluntati"); Nova Vulgata 4:17b is "Deus Abraham … benedictus es". So the Catechism's lettering is not the Nova Vulgata's. It fits the Septuagint's lettering of the Greek (Rahlfs and Göttingen editions), where Mordecai's prayer is 4:17a-i and 4:17b is "Lord, Lord, King who rules over all … there is no one who can oppose you" (added in review; the Rahlfs page itself was not fetched). The CCC cites no other Esther verse (concordance for "esther", [ENG0015/3/JI.HTM](https://www.vatican.va/archive/ENG0015/3/JI.HTM): paragraphs 64, 120 and 489 name the book only).
2. **English Lectionary**, Thursday of the First Week of Lent (Lectionary 227): "Esther C:12, 14-16, 23-25". This uses the NAB letter chapters. Sources: [USCCB, 26 Feb 2026](https://bible.usccb.org/bible/readings/022626.cfm), and the Holy See's own [Vatican News English, 26 Feb 2026](https://www.vaticannews.va/en/word-of-the-day/2026/02/26.html). In WEB-C numbers this is 4:29, 4:31-33 and 4:40-42. The Lectionary's English follows the Latin tradition, not the Greek. "She lay prostrate upon the ground, together with her handmaids, from morning until evening" is Nova Vulgata 4:17p. "As a child I used to hear from the books of my forefathers that you, O LORD, always free those who are pleasing to you" is Nova Vulgata 4:17aa. Neither is in WEB-C's Greek (lines 124-128).
3. **Italian Lectionary**, same day, on [Vatican News Italian, 26 Feb 2026](https://www.vaticannews.va/it/vangelo-del-giorno-e-parola-del-giorno/2026/02/26.html): "Est 4,17k-u". The reading opens with Esther seeking refuge in the Lord, which is Nova Vulgata 4:17n and WEB-C 4:29. In the Septuagint's lettering Esther's prayer opens at 4:17k ("And Esther the queen fled to the Lord, seized with the agony of death"; [Mouton 2023, HTS Teologiese Studies](https://scielo.org.za/scielo.php?script=sci_arttext&pid=S0259-94222023000100009)), so the CEI reading uses the Septuagint's letters, as the Catechism does. The CEI 2008 Esther is translated from the Greek. Verse-by-verse alignment of the Septuagint letters with WEB-C's C 1-30 was not checked: WEB-C has 11 verses for Mordecai's prayer against the Septuagint's 9 letters.

Not found: the Latin *Ordo Lectionum Missae* citation for Lectionary 227, which would show whether the typical edition cites Nova Vulgata letters. No vatican.va copy was found.

Conclusion: no Church source settles a single scheme for the additions in English. The Nova Vulgata settles the Latin, but its letters label an Old Latin text that is not WEB-C's. The Catechism and the Italian Lectionary use the Septuagint's letters, which label the same Greek text WEB-C translates, so they are the closest Church-cited fit for WEB-C, at least at the level of whole prayers.

## 6. Recommendation for 1.4a

**Keep WEB-C numbers, label additions by letter, and record a Nova Vulgata alias per addition (not per verse).**

- References, anchors and `{{v:N}}` markers stay in WEB-C numbers. The restored groups get anchors `esther/4/18`, `esther/4/29` and `esther/10/4` from 1.4a's existing rule (first verse of the group).
- Seed `datapipeline/bible_extra_pericopes.csv` with three rows instead of one block for C. C is about 4,100 characters, and `split_display_passage` would otherwise cut it at an arbitrary point; cutting at the change of speaker keeps the two prayers apart.
  - Esther, 4:18, 4:28, "Addition C: Mordecai's prayer"
  - Esther, 4:29, 4:47, "Addition C: Esther's prayer"
  - Esther, 10:4, 10:14, "Addition F: Mordecai's dream explained"
- Passage metadata may carry `nv_ref` and `nab_ref` for whole additions, where the mapping is exact. (Carter later added `lxx_ref`, the Septuagint range; see "Answered by Carter".) Examples: "Esther 4:17a–kk" and "Esther C:1–30" on the C passages, split as 17a-m / 17n-kk and C 1-11 / C 12-30; "Esther 10:3a–k" and "Esther F:1–11" on F. Do not put Nova Vulgata letters on individual verses. Several WEB-C verses have no Nova Vulgata counterpart, and an alias would claim an equivalence that is not there.
- The pericopes that already hold A, B, D and E (`esther/1/1`, `esther/3/3-*`, `esther/5/1`, `esther/8/1-*`) are untouched by this item. The same per-addition alias can be added to their metadata if 1.4a wants consistency. It changes no text, so the IDs stay.

**Anchors and D1 redirects.** Under this recommendation no existing anchor names different text. `esther/4/4` keeps 4:4-17, because the restored verses form their own group closed at the next pericope start. `esther/10/1` keeps 10:1-3. The three new anchors are new units. **No redirects are needed.**

**If Carter chooses Nova Vulgata renumbering instead,** the cost is:

- (a) A verse map that can only be approximate for C. Some WEB-C verses would have no label.
- (b) Lettered verse numbers. `{{v:N}}` markers, `unit_label` and the chapter/verse parsing in `ingest/bible.py` are integer-only today.
- (c) Changed anchors wherever an addition starts a passage. `esther/1/1` would begin at Nova Vulgata 1:1a. If the anchor followed, it would need a `renumbered` redirect under D1, and 1:1a would hold only part of WEB-C 1:1's text.

The new C and F units need no redirects in either case.

## 7. Plan claims about Esther

The handoff doc is not in the repo. Its Esther claims are carried in the plan's Bible row (plan line 198) and the Decision log.

| Claim | Verdict | Evidence |
|---|---|---|
| Esther 4:18-47 and 10:4-14 are missing (plan, Bible row) | **Holds.** 41 verses. | Section 4, script output; adapter run. |
| 245 missing in total, 244 in the current build | Not re-checked here outside Esther. Esther's share, 41, is confirmed. | Section 4 |
| Bible: "Nova Vulgata numbering" (Inclusion row, plan line 294) and "References match Church documents" (line 199) | **Cannot hold for Esther's additions verse by verse.** Nova Vulgata letters label an Old Latin text that differs from WEB-C's Greek, and English Church documents use other schemes. It holds at the level of whole additions. | Sections 2, 3, 5 |
| Spec: WEB-C intro says additions follow "1:1 … 3:13, 4:17, 8:12, and 10:3" | Partly. A, B, C and F are where the spec says. E is inside 8:13 (line 226), not after 8:12. The intro's "5 additions" counts C and D as one. The 4:17 footnote's "to the end of chapter 5" does not match the brackets, which close at 4:47 (line 142). | Section 1, lines 10, 111, 142, 145, 226 |
| Spec: D "probably the long 5:1. Unverified" | **Corrected:** D is 5:1-2 (lines 145-149), not bracketed. | Section 2 |
| Spec: chapter 9 gap "unexplained" | **Explained:** 9:5 and 9:30, and also 4:6, are Hebrew verses absent from the Greek. | Section 1 |
| Spec: scheme of Nova Vulgata and Church documents "not verified" | **Resolved:** Nova Vulgata uses lettered verses; the Catechism and the Italian Lectionary use the Septuagint's letters; the English Lectionary uses NAB letter chapters. | Sections 2, 5 |

## For Carter

**Recommendation:** keep WEB-C's verse numbers for Esther and title the restored passages by addition letter ("Addition C: Esther's prayer"). Record the Nova Vulgata range (and the NAB letter chapter the English Lectionary uses) in metadata for each whole addition. Restoring C and F then creates three new passages and changes no existing link, so no redirects are needed.

**Why no Church source settles it:**

- The Nova Vulgata numbers the additions as lettered verses (4:17a-kk and so on). Its own preface says the Latin of the additions follows the Old Latin, not the Greek that our WEB-C text translates. Some of our verses have no Nova Vulgata number, and some Nova Vulgata verses have no counterpart in our text.
- Church documents use two schemes, neither the Nova Vulgata's:
  - Catechism ("Esth 4:17b") and Italian Lectionary ("Est 4,17k-u"): the Septuagint's letters (found in review, after Carter's answer);
  - English Lectionary: NAB letter chapters ("Esther C:12…").

**The choice:** which numbering a reader sees on the restored Esther passages. "Numbering" here means the chapter:verse label printed on the passage.

1. **WEB-C numbers with an addition letter** (recommended). Matches the text we actually show; matches no Church document's numbers.
2. **NAB letter chapters** ("Esther C:12-30"). Matches what US Catholics hear at Mass. Needs a non-numeric chapter in references.
3. **Nova Vulgata letters** ("Esther 4:17n-kk"). Matches the Latin standard the Decision log adopted, but only approximately, because the texts differ. It also needs lettered verse support in the adapter.

A related point for later, not part of 1.4a: the English Lectionary's Esther reading follows the Latin text, so a user who searches for the words heard at Mass ("books of my forefathers") will not find them in WEB-C's Esther. Fixing that would mean a different translation, which the plan's "no translations of our own" rule and current sources do not provide.

## Answered by Carter (4 Oct 2026)

Carter accepted the recommendation (before the review found that the Catechism and the Italian Lectionary share the Septuagint's letters): WEB-C numbers with addition-letter titles, Nova Vulgata and NAB ranges in metadata for whole additions. Recorded in `NEEDS-CARTER.md`, the plan's Decision log and the 1.4a spec.

After the review, Carter also approved (4 Oct): record the Septuagint range (`lxx_ref`) alongside the Nova Vulgata and NAB ranges, and correct the Decision log reason to say the Catechism and the Italian Lectionary share the Septuagint's letters. For C, the Septuagint ranges are Mordecai's prayer 4:17a-i and Esther's prayer 4:17k-z, which agree with the Catechism's 4:17b and the Italian Lectionary's 4:17k. Those letters are Rahlfs'; the NETS translation follows the Göttingen edition's C 1-30, the same as WEB-C. F's Septuagint letters were not verified here; 1.4a confirms them from a Rahlfs or Göttingen copy.

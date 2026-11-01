import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from ingest.scripture_notes import scripture_reference  # noqa: E402


@pytest.mark.parametrize("note, ref", [
    ("Matt. xxiv. 15.", "Matt. xxiv. 15."),
    ("2 Kings xx. 7; Isa. xxxviii. 21.", "2 Kings xx. 7; Isa. xxxviii. 21."),
    ("Ex. xx. 12, 13.", "Ex. xx. 12, 13."),
    ("Ps. xliii. 20 (LXX.).", "Ps. xliii. 20 (LXX.)."),
    ("Job xx. 18, LXX.; Prov. xi. 4.", "Job xx. 18, LXX.; Prov. xi. 4."),
    ("Cf. Ex. xx. 12 and Eph. vi. 2, 3.", "Cf. Ex. xx. 12 and Eph. vi. 2, 3."),
    ("[Isa. xxxiii. 17.]", "Isa. xxxiii. 17."),
    # A reference followed by an editor's remark keeps the reference only.
    ("Ps. xxxiv. 8, where Clem. has read Χριστός for χρηστός.", "Ps. xxxiv. 8."),
    ("Matt. xviii. 7. [See R.V.]", "Matt. xviii. 7."),
    ("Heb. x. 25. Barnabas (cap. iv.) reproves the same fault.", "Heb. x. 25."),
    # Sol review, 1.10b: Arabic chapter and verse; a numbered book after a verse list;
    # a colon opening the remark.
    ("Luke 17:21.", "Luke 17:21."),
    ("Comp. 1 Cor. iii. 16, 1 Cor. vi. 19.", "Comp. 1 Cor. iii. 16, 1 Cor. vi. 19."),
    ("Gen. xxxii. 28: Israel = a prince of God.", "Gen. xxxii. 28."),
])
def test_scripture_references_are_kept(note, ref):
    assert scripture_reference(note) == ref


@pytest.mark.parametrize("note", [
    "Literally, “bidding farewell to.”",
    "[A noble utterance from Christian philosophy.]",
    "ἐγγαστριμύθοις.",
    "The ms. has, “and.”",
    "See this series, vol. iii. Elucid. II. p. 630.",
    "Virg., Georg., iii. 112, 102.",
    "Hist. of Susannah 1–3.",
    "In Heb. the word is plural.",
    "A city of Tripolis.",
])
def test_other_notes_are_not(note):
    assert scripture_reference(note) is None

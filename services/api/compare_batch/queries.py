from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class QuerySpec:
    query: str
    category: str  # doctrinal | ethical | pastoral | scriptural | historical
    expected_collections: list[str] = field(default_factory=list)


QUERIES: list[QuerySpec] = [
    # ── Doctrinal (15) ────────────────────────────────────────────────────
    QuerySpec("What is the Trinity?", "doctrinal", ["catechism", "summa", "councils", "bible"]),
    QuerySpec("What does the Church teach about the Real Presence in the Eucharist?", "doctrinal", ["catechism", "summa", "councils"]),
    QuerySpec("What is purgatory?", "doctrinal", ["catechism", "summa", "encyclicals"]),
    QuerySpec("What is the Immaculate Conception?", "doctrinal", ["catechism", "encyclicals", "councils"]),
    QuerySpec("What does the Church teach about papal infallibility?", "doctrinal", ["catechism", "councils", "encyclicals"]),
    QuerySpec("What is sanctifying grace?", "doctrinal", ["catechism", "summa", "encyclicals"]),
    QuerySpec("What are the seven sacraments?", "doctrinal", ["catechism", "summa", "councils"]),
    QuerySpec("What does the Church teach about original sin?", "doctrinal", ["catechism", "summa", "bible", "councils"]),
    QuerySpec("What is the role of Mary in salvation?", "doctrinal", ["catechism", "encyclicals", "apostolic-exhortations"]),
    QuerySpec("What does the Church teach about the resurrection of the body?", "doctrinal", ["catechism", "summa", "bible"]),
    QuerySpec("What is the difference between mortal and venial sin?", "doctrinal", ["catechism", "summa"]),
    QuerySpec("What does the Church teach about angels?", "doctrinal", ["catechism", "summa", "bible"]),
    QuerySpec("What is the communion of saints?", "doctrinal", ["catechism", "encyclicals"]),
    QuerySpec("What does the Church teach about heaven and hell?", "doctrinal", ["catechism", "summa", "bible"]),
    QuerySpec("What is the hypostatic union?", "doctrinal", ["catechism", "summa", "councils"]),

    # ── Ethical (10) ──────────────────────────────────────────────────────
    QuerySpec("How much can we trust our conscience?", "ethical", ["catechism", "summa", "encyclicals"]),
    QuerySpec("What does the Church teach about contraception?", "ethical", ["encyclicals", "catechism"]),
    QuerySpec("What does the Church teach about the death penalty?", "ethical", ["catechism", "encyclicals"]),
    QuerySpec("What does the Church teach about social justice?", "ethical", ["encyclicals", "catechism", "councils"]),
    QuerySpec("What does the Church teach about poverty and wealth?", "ethical", ["encyclicals", "bible", "church-fathers"]),
    QuerySpec("What does the Church teach about war and just peace?", "ethical", ["catechism", "encyclicals", "summa"]),
    QuerySpec("What is the natural law?", "ethical", ["catechism", "summa", "encyclicals"]),
    QuerySpec("What does the Church teach about euthanasia?", "ethical", ["catechism", "encyclicals"]),
    QuerySpec("What does the Church teach about divorce and remarriage?", "ethical", ["catechism", "encyclicals", "bible"]),
    QuerySpec("What does the Church teach about abortion?", "ethical", ["catechism", "encyclicals"]),

    # ── Pastoral (10) ─────────────────────────────────────────────────────
    QuerySpec("Why does God allow suffering?", "pastoral", ["encyclicals", "catechism", "bible", "summa"]),
    QuerySpec("How should I pray?", "pastoral", ["catechism", "apostolic-exhortations", "medieval"]),
    QuerySpec("What is the purpose of the rosary?", "pastoral", ["encyclicals", "apostolic-exhortations"]),
    QuerySpec("How do I discern God's will?", "pastoral", ["apostolic-exhortations", "medieval"]),
    QuerySpec("What is contemplative prayer?", "pastoral", ["catechism", "medieval", "church-fathers"]),
    QuerySpec("How can I grow in holiness?", "pastoral", ["catechism", "apostolic-exhortations", "medieval"]),
    QuerySpec("What is the purpose of fasting and penance?", "pastoral", ["catechism", "church-fathers", "encyclicals"]),
    QuerySpec("Why should Catholics go to confession?", "pastoral", ["catechism", "encyclicals", "apostolic-exhortations"]),
    QuerySpec("What is lectio divina?", "pastoral", ["apostolic-exhortations", "medieval"]),
    QuerySpec("How should a Christian face death?", "pastoral", ["catechism", "encyclicals", "bible"]),

    # ── Scriptural (8) ────────────────────────────────────────────────────
    QuerySpec("What does the Bible teach about love of neighbor?", "scriptural", ["bible", "catechism", "encyclicals"]),
    QuerySpec("What did Jesus teach about forgiveness?", "scriptural", ["bible", "catechism"]),
    QuerySpec("What does Scripture say about the Kingdom of God?", "scriptural", ["bible", "catechism", "encyclicals"]),
    QuerySpec("What does Paul teach about justification by faith?", "scriptural", ["bible", "catechism", "summa"]),
    QuerySpec("What does the New Testament teach about the Body of Christ?", "scriptural", ["bible", "catechism", "encyclicals"]),
    QuerySpec("What does Scripture say about the Holy Spirit?", "scriptural", ["bible", "catechism", "councils"]),
    QuerySpec("What does the Old Testament say about the coming Messiah?", "scriptural", ["bible", "catechism", "church-fathers"]),
    QuerySpec("What does the Gospel of John teach about eternal life?", "scriptural", ["bible", "catechism", "church-fathers"]),

    # ── Historical (7) ────────────────────────────────────────────────────
    QuerySpec("What did the early Church teach about baptism?", "historical", ["church-fathers", "catechism", "councils"]),
    QuerySpec("What did the Church Fathers teach about the Eucharist?", "historical", ["church-fathers", "catechism"]),
    QuerySpec("What did the Council of Nicaea define about Jesus?", "historical", ["councils", "catechism", "church-fathers"]),
    QuerySpec("What did Thomas Aquinas teach about the existence of God?", "historical", ["summa", "medieval"]),
    QuerySpec("How did the Church respond to the Arian heresy?", "historical", ["councils", "church-fathers", "catechism"]),
    QuerySpec("What did Augustine teach about grace and free will?", "historical", ["church-fathers", "catechism", "summa"]),
    QuerySpec("What did the Second Vatican Council teach about the nature of the Church?", "historical", ["councils", "catechism", "encyclicals"]),
]

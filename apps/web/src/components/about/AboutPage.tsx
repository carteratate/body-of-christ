import { COLLECTIONS } from "@/lib/collections";

const COLLECTION_DESCRIPTIONS: Record<string, string> = {
  bible:
    "The Sacred Scriptures of the Catholic Church, comprising 73 books of the Old and New Testaments. Composed by many human authors over roughly 1,500 years under divine inspiration, as understood by the Church. The Bible is the foundation of Christian faith and the starting point for virtually every theological question. Anyone exploring Catholic teaching, prayer, or doctrine will find Scripture woven throughout.",
  catechism:
    "The Catechism of the Catholic Church (CCC), promulgated by Pope John Paul II in 1992. A comprehensive, authoritative summary of Catholic belief and practice, organized into four pillars: the Creed, the Sacraments, the Commandments, and Prayer. Written for anyone who wants to understand what the Church actually teaches, whether a new Catholic, a lifelong believer, or a curious outsider.",
  summa:
    "The masterwork of St. Thomas Aquinas, written between 1265 and 1274. A systematic theological and philosophical synthesis of Christian doctrine, structured as a series of questions, objections, and reasoned replies. Aquinas draws on Scripture, the Church Fathers, and Aristotelian philosophy to address everything from the existence of God to the nature of virtue. Invaluable for anyone interested in the intellectual tradition of the Church, moral theology, or classical philosophy.",
  encyclicals:
    "Formal letters issued by popes to the universal Church, addressing matters of doctrine, morality, and social teaching. Encyclicals carry significant teaching authority and have shaped Catholic thought on topics ranging from labor rights (Rerum Novarum) to marriage (Humanae Vitae) to the nature of faith (Fides et Ratio). Useful for understanding how Catholic teaching has developed and been applied to the questions of each era.",
  councils:
    "The proceedings and documents of the ecumenical councils, the formal gatherings of the world's bishops that define doctrine and address Church affairs. The corpus includes councils from Nicaea (325 AD) through the Second Vatican Council (1962-1965). Council documents are among the most authoritative sources in Catholic theology, defining core beliefs such as the Trinity, the Incarnation, and the nature of the Church.",
  "church-fathers":
    "Writings of the early Christian theologians and bishops from roughly the 1st through 8th centuries, including Ignatius of Antioch, Justin Martyr, Origen, Athanasius, Augustine, and John Chrysostom. The Fathers interpreted Scripture, defended the faith against heresies, and laid the theological foundations the Church still stands on. Essential for understanding how Christian doctrine developed in its earliest centuries.",
  medieval:
    "Theological and philosophical works from the medieval period (roughly 9th through 15th centuries), including scholastic theologians, mystics, and canonists beyond Aquinas. Figures such as Anselm of Canterbury, Bonaventure, Hildegard of Bingen, and Duns Scotus. A rich tradition of rigorous intellectual inquiry paired with deep spiritual reflection, valuable for those interested in how the Church thought through faith and reason across the Middle Ages.",
  "canon-law":
    "The Code of Canon Law (1983), the body of laws governing the Latin Church. Enacted by Pope John Paul II, it codifies the rights and obligations of the faithful, the structure of Church governance, the sacraments, and ecclesiastical procedures. Useful for understanding how the Church operates as an institution and the legal framework underlying pastoral practice.",
  "apostolic-exhortations":
    "Post-synodal documents in which popes synthesize the work of a bishops' synod and offer pastoral guidance to the Church. Notable examples include Evangelii Gaudium (Francis, 2013) on the joy of the Gospel and Familiaris Consortio (John Paul II, 1981) on marriage and family. More pastoral in tone than encyclicals, these documents often address how Catholic teaching should be lived in contemporary life.",
  "papal-documents":
    "A broader category of official papal writings, including apostolic constitutions, apostolic letters, motu proprios, and bulls, that don't fall neatly into the categories above. These documents address a wide range of matters: defining dogmas (such as the Immaculate Conception), reforming Church structures, and issuing pastoral directives. Helpful for tracing specific decisions and pronouncements across pontificates.",
};

export function AboutPage() {
  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-6 max-w-3xl w-full mx-auto">
        <h1 className="text-2xl font-semibold text-brand-primary mb-1">About</h1>
        <p className="text-brand-muted text-sm mb-8">
          What Body of Christ is and what&apos;s in the corpus.
        </p>

        {/* Mission */}
        <section className="mb-10">
          <p className="text-brand-muted text-[10px] uppercase tracking-widest font-medium mb-3 pb-2 border-b border-brand-surface">
            Our Mission
          </p>
          <div className="text-brand-primary text-sm leading-relaxed">
            <p>
              For over two thousand years, Christians have wrestled with questions
              surrounding suffering, virtue, justice, grace, salvation, human
              nature, and God Himself. Those conversations have occurred over
              Scripture, catechisms, encyclicals, writings of the early church
              fathers, the lives of the saints, and more. The Body of Christ
              brings their wisdom together into one place, allowing you to explore
              the Catholic tradition through the people who built, defended, and
              passed down the fullness of the faith.
            </p>
          </div>
        </section>

        {/* Collections */}
        <section>
          <p className="text-brand-muted text-[10px] uppercase tracking-widest font-medium mb-3 pb-2 border-b border-brand-surface">
            Collections
          </p>
          <div className="space-y-3">
            {COLLECTIONS.map(({ key, label, color }) => {
              const description = COLLECTION_DESCRIPTIONS[key];
              if (!description) return null;
              return (
                <div key={key} className="rounded bg-brand-surface px-3 py-3">
                  <span
                    className="text-xs font-semibold px-2.5 py-0.5 rounded-full border"
                    style={{ color, borderColor: color }}
                  >
                    {label}
                  </span>
                  <p className="text-brand-muted text-xs leading-relaxed mt-2">
                    {description}
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}

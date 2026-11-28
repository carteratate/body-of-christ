import Link from "next/link";
import { COLLECTIONS } from "@/lib/collections";

const COLLECTION_DESCRIPTIONS: Record<string, string> = {
  bible:
    "The Sacred Scriptures of the Catholic Church, comprising 73 books of the Old and New Testaments. Composed by many human authors over roughly 1,500 years under divine inspiration, as understood by the Church. The Bible is the foundation of Christian faith and the starting point for virtually every theological question. Anyone exploring Catholic teaching, prayer, or doctrine will find Scripture woven throughout.",
  catechism:
    "The Catechism of the Catholic Church (CCC), promulgated by Pope John Paul II in 1992. A comprehensive, authoritative summary of Catholic belief and practice, organized into four pillars: the Creed, the Sacraments, the Commandments, and Prayer. Written for anyone who wants to understand what the Church actually teaches, whether a new Catholic, a lifelong believer, or a curious outsider. The collection also holds the Compendium of the Catechism of the Catholic Church (2005), a summary of the CCC's teaching in 598 questions and answers, and the Catechism of the Council of Trent (1566), the Roman Catechism, in John A. McHugh and Charles J. Callan's 1923 translation: a historical catechism, so for current teaching see the CCC.",
  summa:
    "The masterwork of St. Thomas Aquinas, written between 1265 and 1274. A systematic theological and philosophical synthesis of Christian doctrine, structured as a series of questions, objections, and reasoned replies. Aquinas draws on Scripture, the Church Fathers, and Aristotelian philosophy to address everything from the existence of God to the nature of virtue. Invaluable for anyone interested in the intellectual tradition of the Church, moral theology, or classical philosophy.",
  papal:
    "Letters and acts of the popes addressed to the whole Church, from Unam Sanctam (Boniface VIII, 1302) to the present: encyclicals, apostolic exhortations, apostolic letters and constitutions, a motu proprio and the Syllabus of Errors. Encyclicals such as Rerum Novarum, Humanae Vitae and Fides et Ratio set out teaching on doctrine, morality and society. Exhortations such as Familiaris Consortio and Evangelii Gaudium give pastoral guidance, often gathering up the work of a synod. Letters, constitutions and bulls record particular decisions, from Ineffabilis Deus to Ordinatio Sacerdotalis. Use the arrow on the Papal documents button to search only some kinds of document, or only some popes.",
  councils:
    "The proceedings and documents of the ecumenical councils, the formal gatherings of the world's bishops that define doctrine and address Church affairs. The corpus includes councils from Nicaea (325 AD) through the Second Vatican Council (1962-1965). Council documents are among the most authoritative sources in Catholic theology, defining core beliefs such as the Trinity, the Incarnation, and the nature of the Church.",
  "church-fathers":
    "Writings of the early Church Fathers from roughly the 1st through 6th centuries, including Clement of Rome, Ignatius of Antioch, Justin Martyr, Irenaeus, Cyprian, Athanasius and Augustine. The Fathers interpreted Scripture, defended the faith against heresies, and laid the theological foundations the Church still stands on. Essential for understanding how Christian doctrine developed in its earliest centuries.",
  theologians:
    "Theologians and spiritual writers after the age of the Fathers. For now it holds medieval works: Anselm of Canterbury, Bernard of Clairvaux and Thomas à Kempis's Imitation of Christ. A tradition that pairs rigorous inquiry with deep spiritual reflection; soon more writers will join it.",
  "roman-curia":
    "Doctrinal documents of the Dicastery for the Doctrine of the Faith, the office of the Roman Curia that helps the Pope safeguard Catholic teaching on faith and morals (the Congregation for the Doctrine of the Faith until 2022). Sixty declarations, instructions, doctrinal notes, letters and formal responses from 1966 to 2026, many expressly approved by the Pope: from Persona Humana and Donum Vitae to Dominus Iesus, Dignitas Personae and Dignitas Infinita. They are the Church's most direct answers to modern doctrinal and moral questions: bioethics and IVF, end-of-life care, human dignity, artificial intelligence, the priesthood, and the Church's relationship to other religions. Use the arrow on the Roman Curia button to search only some kinds of document.",
  "church-law":
    "The Code of Canon Law (1983), the body of laws governing the Latin Church, promulgated by Pope John Paul II. It sets out the rights and obligations of the faithful, the structure of Church governance, the sacraments and the Church's procedures. Useful for understanding how the Church works as an institution and the legal framework behind pastoral practice.",
};

export function AboutPage({ isGuest = false }: { isGuest?: boolean }) {
  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-6 max-w-3xl w-full mx-auto">
        <h1 className="text-2xl font-semibold text-brand-primary mb-4">About</h1>

        {/* Mission */}
        <section className="mb-10">
          <p className="text-brand-muted text-[10px] uppercase tracking-widest font-medium mb-3 pb-2 border-b border-brand-surface">
            Our Mission
          </p>
          <p className="text-brand-primary text-sm leading-relaxed">
            For over two thousand years, Christians have wrestled with questions
            surrounding suffering, virtue, justice, grace, salvation, human
            nature, and more. Those conversations have occurred over
            Scripture, catechisms, encyclicals, writings of the early church
            fathers, church councils, etc. TheoCorpus
            brings their wisdom together into one place, allowing you to explore
            the Catholic tradition through the people who built, defended, and
            passed down the fullness of the faith.
          </p>
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

        {/* Sources (corpus cleanup 4.4) */}
        <section className="mt-10">
          <p className="text-brand-muted text-[10px] uppercase tracking-widest font-medium mb-3 pb-2 border-b border-brand-surface">
            Sources
          </p>
          <p className="text-brand-primary text-sm leading-relaxed">
            Where the texts come from, and on what basis:{" "}
            <Link href={isGuest ? "/guest/about/sources" : "/about/sources"} className="underline underline-offset-2 hover:decoration-2">
              Sources
            </Link>
            .
          </p>
        </section>
      </div>
    </div>
  );
}

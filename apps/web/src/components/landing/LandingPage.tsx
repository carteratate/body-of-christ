import Link from "next/link";

export function LandingPage({ href = "/search/guest" }: { href?: string }) {
  return (
    <div className="min-h-full bg-brand-bg flex flex-col items-center justify-center px-6 py-16">
      <div className="max-w-2xl w-full">
        <h1 className="text-brand-accent font-semibold leading-tight mb-10 text-center" style={{ fontFamily: "var(--font-cinzel)", fontSize: "clamp(2.5rem, 8vw, 5rem)" }}>
          TheoCorpus
        </h1>
        <div className="text-brand-primary text-base leading-relaxed mb-12">
          <p>
            TheoCorpus uses AI to find relevant passages across Scripture, the Catechism, Church Fathers, Aquinas, councils, encyclicals, and papal documents. Instead of generating an answer and asking you to trust it, TheoCorpus takes you directly to the texts of the Catholic tradition.
          </p>
        </div>
        <div className="flex justify-center">
          <Link href={href} className="inline-block bg-brand-accent text-brand-bg rounded-lg px-10 py-3 text-lg font-semibold hover:opacity-90 transition-opacity" style={{ fontFamily: "var(--font-cinzel)" }}>
            Get Started
          </Link>
        </div>
      </div>
    </div>
  );
}

import { redirect } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

export const metadata = {
  title: "Body of Christ",
  description:
    "Explore two thousand years of Catholic wisdom — Scripture, catechisms, encyclicals, the Church Fathers, and more.",
};

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Returning users go straight to the app.
  if (user) redirect("/search");

  return (
    <div className="min-h-full bg-brand-bg flex flex-col items-center justify-center px-6 py-16">
      <div className="max-w-2xl w-full">

        {/* Title */}
        <h1
          className="text-brand-accent font-semibold leading-tight mb-10 text-center"
          style={{ fontFamily: "var(--font-cinzel)", fontSize: "clamp(2.5rem, 8vw, 5rem)" }}
        >
          Body of Christ
        </h1>

        {/* Mission statement */}
        <div className="space-y-5 text-brand-primary text-base leading-relaxed mb-12">
          <p>
            At the Body of Christ, we believe that while AI and LLMs are
            incredibly useful tools, fields centered around truth, meaning,
            morality, theology, and the human condition are better served to be
            studied through the wisdom of real people. The goal of this project
            is to make the accumulated knowledge of the Church more accessible
            to everyone.
          </p>
          <p>
            For over two thousand years, Christians have wrestled with questions
            surrounding suffering, virtue, justice, grace, salvation, human
            nature, and God Himself. Those conversations have occurred over
            Scripture, catechisms, encyclicals, writings of the early church
            fathers, the lives of the saints, and more. The Body of Christ
            brings their wisdom together into one place, allowing you to explore
            the Catholic tradition through the people who built, defended,
            and passed down the fullness of the faith.
          </p>
        </div>

        {/* CTA */}
        <div className="flex justify-center">
          <Link
            href="/login"
            className="inline-block bg-brand-accent text-brand-bg rounded-lg px-10 py-3 text-lg font-semibold hover:opacity-90 transition-opacity"
            style={{ fontFamily: "var(--font-cinzel)" }}
          >
            Get Started
          </Link>
        </div>

      </div>
    </div>
  );
}

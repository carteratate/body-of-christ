import Link from "next/link";

export const metadata = { title: "Privacy Policy — TheoCorpus" };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="mb-3 border-b border-brand-surface pb-2 text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        {title}
      </h2>
      <div className="space-y-3 text-sm leading-relaxed text-brand-primary">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <div className="min-h-full overflow-y-auto bg-brand-bg">
      <div className="mx-auto w-full max-w-3xl px-6 py-8">
        <Link href="/" className="text-sm text-brand-accent hover:opacity-80">
          ← TheoCorpus
        </Link>
        <h1 className="mb-1 mt-4 text-2xl font-semibold text-brand-primary">Privacy Policy</h1>
        <p className="mb-8 text-sm text-brand-muted">Effective September 27, 2026</p>

        <Section title="What we collect">
          <p>
            <strong>Account details.</strong> When you create an account we store your email address. If you
            sign in with Google, Google shares your name, email address, and profile picture with us; we do
            not receive your Google password or access to any other Google data.
          </p>
          <p>
            <strong>What you do in TheoCorpus.</strong> Your searches and their results, saved passages and
            the notes you attach to them, your reading position in documents, your preferences, and any
            feedback you send.
          </p>
          <p>
            <strong>Trial searches.</strong> If you search before creating an account, those searches are
            stored against a random token kept in your browser, so they can move into your account if you
            sign up.
          </p>
          <p>
            <strong>Usage analytics.</strong> We record product events (for example, that a search was run)
            to understand how TheoCorpus is used. We do not record your screen or sessions.
          </p>
        </Section>

        <Section title="How we use it">
          <p>
            To run the service: answer your searches, keep your history and saved passages, and remember
            your settings. To improve search quality and fix problems. We do not sell your information and
            we do not use it for advertising.
          </p>
        </Section>

        <Section title="Who processes it">
          <p>
            TheoCorpus relies on service providers that process data on our behalf: Supabase (accounts and
            database), Vercel and our API host (hosting), Qdrant (search index), PostHog (analytics), and
            OpenAI, Anthropic, and Cohere, which receive the text of your search to find and explain
            relevant passages. Each processes data only to provide its service to us.
          </p>
        </Section>

        <Section title="Your choices">
          <p>
            You can delete individual searches from your history and remove saved passages at any time. To
            delete your account and everything associated with it, or to ask what we hold about you, send a
            request through the{" "}
            <Link href="/guest/feedback" className="text-brand-accent hover:opacity-80">
              feedback form
            </Link>{" "}
            and include the email address on your account.
          </p>
        </Section>

        <Section title="Changes">
          <p>
            If this policy changes, we will update this page and its effective date.
          </p>
        </Section>
      </div>
    </div>
  );
}

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

        <div className="mb-10 rounded-xl border border-brand-surface bg-brand-surface p-5">
          <p className="mb-3 text-sm font-semibold text-brand-primary">The short version</p>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-brand-primary">
            <li>We save your searches, saved passages, and notes so they&apos;re there when you come back. Other people using TheoCorpus can&apos;t see them.</li>
            <li>We don&apos;t sell your data, and there are no ads.</li>
            <li>Our analytics aren&apos;t tied to your account and never record what you searched.</li>
            <li>You can delete searches and saved passages yourself. Ask us and we&apos;ll delete your whole account.</li>
          </ul>
        </div>

        <Section title="What we save">
          <p>
            When you make an account, we save your email address so you can sign in. If you sign in with Google,
            Google also gives us your name and profile picture, and we save those too. We never see your Google
            password.
          </p>
          <p>
            Once you&apos;re signed in, we save your searches and the passages each one found, the passages you
            bookmark, any notes you write on them, where you stopped reading, and your settings. That&apos;s how
            your history and saved passages work. All of it is attached to your account.
          </p>
          <p>
            You can try a few searches before making an account. Those are saved under a random code in your
            browser, not under a name. If you sign up later, we move them into your account.
          </p>
          <p>If you send us feedback, we keep what you wrote.</p>
        </Section>

        <Section title="Analytics">
          <p>
            We count things like how many searches run each day. Those counts aren&apos;t tied to your account, and
            they never include the words you typed. We don&apos;t record your screen.
          </p>
        </Section>

        <Section title="IP addresses">
          <p>
            Every website sees your IP address when you load a page, and so do the companies that host and measure
            ours. We use it to cap free trial searches and block feedback spam. For that we store a one-way hash of
            it, which can&apos;t be turned back into the address.
          </p>
        </Section>

        <Section title="Cookies and browser storage">
          <p>
            One cookie keeps you signed in and another remembers light or dark mode. Your browser also holds your
            trial code, passages you saved before signing up, and reader settings like font and line spacing.
            PostHog, our analytics tool, sets its own cookie so a returning visitor isn&apos;t counted twice.
            On the sign-in page, Google&apos;s button can read Google&apos;s own cookies to show which account
            you&apos;re signed in to. We don&apos;t use ad cookies.
          </p>
        </Section>

        <Section title="Companies we work with">
          <p>
            TheoCorpus runs on Supabase, Vercel, OpenAI, Railway, Qdrant, Anthropic, PostHog, and Cohere. Some of
            them handle the text of your searches, because that&apos;s how we find matching
            passages. We send them the search text only, never your name or email address.
          </p>
          <p>
            The sign-in and sign-up pages load Google&apos;s sign-in button. That means Google sees visits to
            those pages, including their IP address, even if you sign in with email.
          </p>
        </Section>

        <Section title="Deleting your data">
          <p>
            You can delete any search from your history, and remove any saved passage, whenever you want. To delete
            your whole account, or to find out what we hold about you, send a note through the{" "}
            <Link href="/guest/feedback" className="text-brand-accent hover:opacity-80">
              feedback form
            </Link>{" "}
            with your account&apos;s email address and we&apos;ll handle it.
          </p>
        </Section>

        <Section title="Changes">
          <p>If this policy changes, we&apos;ll update this page and the date at the top.</p>
        </Section>
      </div>
    </div>
  );
}

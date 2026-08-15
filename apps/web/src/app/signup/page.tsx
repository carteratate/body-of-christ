import { LoginForm } from "@/components/auth/LoginForm";

export const metadata = { title: "Create an account — TheoCorpus" };

export default function SignupPage() {
  return (
    <div className="flex min-h-full items-center justify-center bg-brand-bg px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="font-brand text-3xl font-semibold text-brand-accent">TheoCorpus</h1>
          <p className="mt-2 text-sm text-brand-muted">Keep your searches, saved passages, and private notes</p>
        </div>
        <div className="rounded-xl border border-brand-surface bg-brand-surface p-6">
          <LoginForm initialMode="sign-up" />
        </div>
      </div>
    </div>
  );
}

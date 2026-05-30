import { LoginForm } from "@/components/auth/LoginForm";

export const metadata = { title: "Sign in — Body of Christ" };

export default function LoginPage() {
  return (
    <div className="flex min-h-full items-center justify-center bg-brand-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-semibold tracking-tight text-brand-accent">
            Body of Christ
          </h1>
          <p className="mt-2 text-sm text-brand-muted">
            Explore Catholic theology through conversation
          </p>
        </div>

        <div className="rounded-xl border border-brand-surface bg-brand-surface p-6">
          <LoginForm />
        </div>
      </div>
    </div>
  );
}

"use client";

import { Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { ReaderMobileStatusHeader } from "@/components/reader/ReaderMobileStatusHeader";

function Pulse({ className }: { className: string }) {
  return <div className={`rounded bg-brand-surface ${className}`} />;
}

function PageFrame({ children, width = "max-w-3xl" }: { children: React.ReactNode; width?: string }) {
  return <div className="h-full overflow-y-auto" aria-busy="true" aria-live="polite"><div className={`mx-auto w-full min-w-0 px-4 py-5 sm:px-6 sm:py-6 ${width}`}><div className="animate-pulse">{children}</div></div></div>;
}

export function SavedPassagesSkeleton() {
  return <PageFrame><h1 className="mb-5 text-2xl font-semibold text-brand-primary">Saved Passages</h1><Pulse className="mb-5 h-12 w-full" /><div className="space-y-3">{[0, 1, 2].map((item) => <Pulse key={item} className="h-44 w-full rounded-lg" />)}</div></PageFrame>;
}

export function HistorySkeleton() {
  return <PageFrame><div className="mb-5"><h1 className="text-2xl font-semibold text-brand-primary">Search History</h1><p className="mt-1 text-sm text-brand-muted">Return to previous questions and their sources.</p></div><Pulse className="mb-6 h-12 w-full" /><Pulse className="mb-3 h-3 w-16" /><div className="space-y-2">{[0, 1, 2, 3, 4].map((item) => <Pulse key={item} className="h-12 w-full" />)}</div></PageFrame>;
}

export function LibrarySkeleton() {
  return <PageFrame><h1 className="mb-1 text-2xl font-semibold text-brand-primary">Library</h1><p className="mb-6 text-sm text-brand-muted">All documents included in the search corpus.</p><Pulse className="mb-3 h-12 w-full" /><Pulse className="mb-7 h-10 w-full" /><section className="mb-8"><h2 className="mb-3 text-base font-semibold text-brand-primary">Continue Reading</h2><div className="grid gap-2 sm:grid-cols-2"><Pulse className="h-20 w-full" /><Pulse className="h-20 w-full" /></div></section><div className="space-y-8">{[0, 1, 2].map((section) => <section key={section} className="space-y-2"><div className="flex items-center gap-3 border-b border-brand-surface pb-2"><Pulse className="h-5 w-28" /><Pulse className="h-4 w-36" /></div>{[0, 1, 2].map((row) => <Pulse key={row} className="h-10 w-full" />)}</section>)}</div></PageFrame>;
}

export function SearchPageSkeleton() {
  return <div className="flex h-full min-h-0 flex-col" aria-busy="true" aria-live="polite"><div className="flex flex-1 flex-col items-center justify-center px-4 py-12 animate-pulse"><Pulse className="mb-7 h-8 w-56" /><div className="grid w-full max-w-2xl grid-cols-2 gap-3 max-sm:grid-cols-1">{[0, 1, 2, 3].map((item) => <Pulse key={item} className="h-[4.5rem] w-full rounded-xl" />)}</div><Pulse className="mt-6 h-11 w-44 rounded-md" /></div><div className="shrink-0 border-t border-brand-surface bg-brand-bg px-4 py-3 pb-4 max-md:pb-[calc(1rem+env(safe-area-inset-bottom))]"><div className="mb-2 flex items-center justify-between gap-3 max-md:flex-col max-md:items-stretch max-md:gap-2 animate-pulse"><div className="flex flex-wrap gap-2">{[0, 1, 2, 3, 4, 5].map((item) => <Pulse key={item} className="h-8 w-24 rounded-full" />)}</div><Pulse className="h-8 w-32 shrink-0" /></div><Pulse className="h-12 w-full" /></div></div>;
}

export function ReaderOverviewSkeleton() {
  return <div className="flex h-full flex-col bg-brand-bg" aria-busy="true" aria-live="polite"><ReaderMobileStatusHeader /><div className="mx-auto w-full max-w-3xl flex-1 space-y-4 px-4 py-6 sm:px-6 animate-pulse"><Pulse className="h-5 w-24" /><Pulse className="h-10 w-2/3" /><Pulse className="h-24 w-full" /><div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((item) => <Pulse key={item} className="h-12 w-full" />)}</div></div></div>;
}

export function ReaderChapterSkeleton() {
  return <div className="flex h-full flex-col" aria-busy="true" aria-live="polite"><header className="border-b border-brand-surface bg-brand-bg px-2 py-2 sm:px-4 animate-pulse"><ReaderMobileStatusHeader embedded /><div className="mt-1 flex min-h-10 flex-wrap items-center gap-2 md:mt-0 md:flex-nowrap"><div className="min-w-0 basis-full px-1 md:max-w-[18rem] md:basis-auto md:shrink"><Pulse className="h-4 w-48" /><Pulse className="mt-1 h-3 w-32" /></div><Pulse className="h-9 w-24" /><Pulse className="h-9 w-32" /><Pulse className="ml-auto h-10 w-10" /></div><div className="mt-1 flex items-center justify-between gap-2 border-t border-brand-surface pt-2"><Pulse className="h-9 w-24" /><Pulse className="h-9 w-20" /></div></header><div className="mx-auto w-full max-w-3xl flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-6 animate-pulse"><Pulse className="h-7 w-2/3" />{[0, 1, 2, 3, 4].map((item) => <Pulse key={item} className="h-24 w-full" />)}</div></div>;
}

export function ReaderPageSkeleton() {
  const searchParams = useSearchParams();
  return searchParams.get("chapter") || searchParams.get("anchor") ? <ReaderChapterSkeleton /> : <ReaderOverviewSkeleton />;
}

function SourceGuideSkeleton() {
  return <PageFrame><h1 className="mb-6 text-2xl font-semibold text-brand-primary">Source Guide</h1><Pulse className="h-12 w-full" /><Pulse className="mt-4 h-11 w-28" /><Pulse className="mt-6 h-32 w-full rounded-lg" /></PageFrame>;
}

export function SettingsPageSkeleton() {
  return <div className="max-w-lg p-6 animate-pulse" aria-busy="true" aria-live="polite"><div className="mb-6 flex items-center gap-2"><Pulse className="h-5 w-5" /><h1 className="text-xl font-semibold text-brand-primary">Settings</h1></div>{["h-24", "h-20", "h-20"].map((height, item) => <Pulse key={item} className={`${item ? "mt-4" : ""} ${height} w-full rounded-lg`} />)}</div>;
}

function FeedbackPageSkeleton() {
  return <PageFrame width="max-w-2xl"><h1 className="text-2xl font-semibold text-brand-primary">Feedback &amp; bug reports</h1><Pulse className="mt-2 h-10 w-full" /><div className="mt-7 space-y-6"><Pulse className="h-5 w-52" /><div className="grid gap-2 sm:grid-cols-2">{[0, 1, 2, 3].map((item) => <Pulse key={item} className="h-[4.5rem] w-full" />)}</div><Pulse className="h-5 w-20" /><Pulse className="h-52 w-full" /><Pulse className="h-16 w-full" /><Pulse className="h-11 w-36" /></div></PageFrame>;
}

function AboutPageSkeleton() {
  return <div className="h-full overflow-y-auto" aria-busy="true" aria-live="polite"><div className="mx-auto w-full max-w-3xl px-6 py-6 animate-pulse"><h1 className="mb-4 text-2xl font-semibold text-brand-primary">About</h1><section className="mb-10"><Pulse className="mb-3 h-6 w-full" /><Pulse className="h-24 w-full" /></section><section><Pulse className="mb-3 h-6 w-full" /><div className="space-y-3">{Array.from({ length: 10 }).map((_, item) => <Pulse key={item} className="h-28 w-full" />)}</div></section></div></div>;
}

function AuthPageSkeleton({ signUp = false }: { signUp?: boolean }) {
  return <div className="flex min-h-full items-center justify-center bg-brand-bg px-4 py-8" aria-busy="true" aria-live="polite"><div className="w-full max-w-sm animate-pulse"><div className="mb-8 text-center"><h1 className="text-3xl font-semibold text-brand-accent">TheoCorpus</h1><Pulse className="mx-auto mt-2 h-4 w-64" /></div><div className="rounded-xl border border-brand-surface bg-brand-surface p-6"><h2 className="text-center text-lg font-semibold text-brand-primary">{signUp ? "Create an account" : "Sign in"}</h2><div className="mt-4 space-y-4"><Pulse className="h-16 w-full" /><Pulse className="h-16 w-full" />{signUp && <Pulse className="h-16 w-full" />}<Pulse className="h-11 w-full" /></div></div></div></div>;
}

function PasswordResetSkeleton() {
  return <div className="flex min-h-full items-center justify-center bg-brand-bg px-4" aria-busy="true" aria-live="polite"><div className="w-full max-w-sm animate-pulse"><div className="mb-8 text-center"><h1 className="text-3xl font-semibold text-brand-accent">TheoCorpus</h1><Pulse className="mx-auto mt-2 h-4 w-44" /></div><Pulse className="h-64 w-full rounded-xl" /></div></div>;
}

function LandingPageSkeleton() {
  return <div className="flex min-h-full flex-col items-center justify-center bg-brand-bg px-6 py-16" aria-busy="true" aria-live="polite"><div className="w-full max-w-2xl animate-pulse"><h1 className="mb-10 text-center text-5xl font-semibold text-brand-accent sm:text-7xl">TheoCorpus</h1><div className="mb-12 space-y-3"><Pulse className="h-5 w-full" /><Pulse className="h-5 w-full" /><Pulse className="h-5 w-5/6" /></div><Pulse className="mx-auto h-12 w-40 rounded-lg" /></div></div>;
}

export function DestinationPageSkeleton() {
  const pathname = usePathname();
  if (pathname.startsWith("/sources")) return <LibrarySkeleton />;
  if (pathname.startsWith("/bookmarks")) return <SavedPassagesSkeleton />;
  if (pathname.startsWith("/history")) return <HistorySkeleton />;
  if (pathname.startsWith("/reader")) return <Suspense fallback={<ReaderOverviewSkeleton />}><ReaderPageSkeleton /></Suspense>;
  if (pathname.startsWith("/search")) return <SearchPageSkeleton />;
  if (pathname.startsWith("/settings")) return <SettingsPageSkeleton />;
  if (pathname.startsWith("/discover")) return <SourceGuideSkeleton />;
  if (pathname.startsWith("/feedback")) return <FeedbackPageSkeleton />;
  if (pathname.startsWith("/about")) return <AboutPageSkeleton />;
  if (pathname === "/guest/about") return <AboutPageSkeleton />;
  if (pathname === "/guest/feedback") return <FeedbackPageSkeleton />;
  if (pathname === "/login") return <AuthPageSkeleton />;
  if (pathname === "/signup") return <AuthPageSkeleton signUp />;
  if (pathname === "/update-password") return <PasswordResetSkeleton />;
  if (pathname === "/" || pathname.startsWith("/onboarding-preview")) return <LandingPageSkeleton />;
  if (pathname.startsWith("/auth/callback")) return <PasswordResetSkeleton />;
  return <LandingPageSkeleton />;
}

import { notFound } from "next/navigation";
import { LandingPage } from "@/components/landing/LandingPage";
import { PreviewReset } from "@/components/landing/PreviewReset";

export const metadata = { title: "Onboarding Preview — TheoCorpus" };

export default function OnboardingPreviewPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <><PreviewReset /><LandingPage href="/search/guest?preview=1" /></>;
}

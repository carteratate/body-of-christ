import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { LandingPage } from "@/components/landing/LandingPage";

export const metadata = {
  title: "TheoCorpus",
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

  return <LandingPage />;
}

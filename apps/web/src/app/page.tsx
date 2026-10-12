import { LandingPage } from "@/components/landing/LandingPage";

export const metadata = {
  title: "TheoCorpus",
  description:
    "Explore two thousand years of Catholic wisdom — Scripture, catechisms, encyclicals, the Church Fathers, and more.",
};

// Returning users never reach this page: the middleware redirects a signed-in
// visitor on "/" to /search, carrying any refreshed session cookies.
export default function HomePage() {
  return <LandingPage />;
}

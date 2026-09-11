import { notFound } from "next/navigation";
import { QuotaTenPrototype } from "./QuotaTenPrototype";

export const metadata = { title: "Single-source 10 prototype | TheoCorpus" };

export default function QuotaTenPrototypePage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <QuotaTenPrototype />;
}

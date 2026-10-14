import type { Metadata } from "next";
import { Geist, Geist_Mono, Judson } from "next/font/google";
import { cookies } from "next/headers";
import "./globals.css";
import { PostHogProvider } from "@/components/layout/PostHogProvider";
import { AuthenticatedRouteShell } from "@/components/layout/AuthenticatedRouteShell";

// Brand heading font, set in capitals by .font-brand in globals.css.
const judson = Judson({
  variable: "--font-judson",
  subsets: ["latin"],
  weight: ["400"],
});

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TheoCorpus",
  description:
    "Search Scripture, Church teaching, and two thousand years of Catholic writing. Find relevant passages and read them in context.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const theme = cookieStore.get("theocorpus-theme")?.value;

  return (
    <html
      lang="en"
      suppressHydrationWarning
      data-theme={theme === "light" ? "light" : undefined}
      className={`${judson.variable} ${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="h-full antialiased">
        <PostHogProvider>
          <AuthenticatedRouteShell>{children}</AuthenticatedRouteShell>
        </PostHogProvider>
      </body>
    </html>
  );
}

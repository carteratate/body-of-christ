import type { Metadata } from "next";
import { Cinzel, Geist, Geist_Mono } from "next/font/google";
import { cookies } from "next/headers";
import "./globals.css";
import { PostHogProvider } from "@/components/layout/PostHogProvider";

const cinzel = Cinzel({
  variable: "--font-cinzel",
  subsets: ["latin"],
  weight: ["600"],
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
  title: "Body of Christ",
  description: "Explore Catholic theology through conversation",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const theme = cookieStore.get("boc-theme")?.value;

  return (
    <html
      lang="en"
      suppressHydrationWarning
      data-theme={theme === "light" ? "light" : undefined}
      className={`${cinzel.variable} ${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="h-full antialiased">
        <PostHogProvider>{children}</PostHogProvider>
      </body>
    </html>
  );
}

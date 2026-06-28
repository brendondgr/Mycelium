import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono, Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { AppShell } from "@/components/layout/app-shell";
import { BodyHydrationGuard } from "@/components/layout/body-hydration-guard";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  preload: false,
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  preload: false,
});

// Brand typography (Mycelium style guide): Fraunces for scholarly headings,
// Inter for UI/body. Used by the auth and onboarding surfaces.
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  preload: false,
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  preload: false,
});

export const metadata: Metadata = {
  title: "Mycelium",
  description: "Lab intelligence for research teams.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} ${inter.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body suppressHydrationWarning>
        <BodyHydrationGuard />
        <AppShell>
          <Providers>{children}</Providers>
        </AppShell>
      </body>
    </html>
  );
}

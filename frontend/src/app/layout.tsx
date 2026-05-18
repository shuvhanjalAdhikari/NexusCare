// ================================================================
// NexusCare — Root Layout
// Loads the Inter typeface, applies global tokens, wraps all routes.
// ================================================================
import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

// Inter is the design system typeface (§2). next/font exposes it as
// the --font-sans CSS variable consumed by globals.css.
const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "NexusCare",
  description: "Multi-tenant hospital OPD management platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}

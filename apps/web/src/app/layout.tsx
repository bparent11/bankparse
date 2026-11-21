import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { WalletCards } from "lucide-react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { SpaceSwitcher } from "@/components/space-switcher";
import { ThemeSwitcher } from "@/components/theme-switcher";

import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "bankparse", template: "%s · bankparse" },
  description: "Importez vos relevés bancaires PDF et retrouvez toutes vos opérations au même endroit.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-background text-foreground">
        <Providers>
          <div className="flex min-h-screen flex-col md:flex-row">
            <aside className="flex flex-col border-b border-sidebar-border bg-sidebar p-3 text-sidebar-foreground md:sticky md:top-0 md:h-screen md:w-60 md:overflow-y-auto md:shrink-0 md:border-r md:border-b-0 md:p-4">
              <div className="mb-2 flex items-center justify-between gap-2 md:mb-6">
                <Link href="/" className="flex items-center gap-2.5 px-2 py-1.5 text-base font-semibold tracking-tight">
                  <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
                    <WalletCards className="size-4.5" />
                  </span>
                  bankparse
                </Link>
                <ThemeSwitcher className="flex md:hidden" />
              </div>
              <SpaceSwitcher />
              <AppNav />
              <ThemeSwitcher className="mt-auto hidden pt-4 md:flex" />
            </aside>
            <main className="min-w-0 flex-1">
              <div className="mx-auto max-w-6xl p-4 md:p-8">{children}</div>
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}

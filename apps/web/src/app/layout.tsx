import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { WalletCards } from "lucide-react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";

import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "bankparse", template: "%s · bankparse" },
  description: "Importez vos relevés bancaires PDF et retrouvez toutes vos opérations au même endroit.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full bg-background text-foreground">
        <Providers>
          <div className="mx-auto flex min-h-screen max-w-7xl flex-col md:flex-row">
            <aside className="border-b p-3 md:sticky md:top-0 md:h-screen md:w-56 md:shrink-0 md:border-r md:border-b-0 md:p-4">
              <Link href="/" className="mb-2 flex items-center gap-2 px-3 py-2 font-semibold md:mb-6">
                <WalletCards className="size-5" />
                bankparse
              </Link>
              <AppNav />
            </aside>
            <main className="min-w-0 flex-1 p-4 md:p-8">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}

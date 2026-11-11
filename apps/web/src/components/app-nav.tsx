"use client";

import { FileStack, Landmark, LayoutDashboard, ListOrdered, Upload } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Vue d'ensemble", icon: LayoutDashboard },
  { href: "/import", label: "Importer", icon: Upload },
  { href: "/operations", label: "Opérations", icon: ListOrdered },
  { href: "/comptes", label: "Comptes", icon: Landmark },
  { href: "/fichiers", label: "Fichiers", icon: FileStack },
];

export function AppNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto md:flex-col" aria-label="Navigation principale">
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              active && "bg-muted text-foreground",
            )}
          >
            <Icon className="size-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

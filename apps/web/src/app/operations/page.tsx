import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import { OperationsView } from "./operations-view";

export const metadata: Metadata = { title: "Opérations" };

export default function OperationsPage() {
  return (
    // OperationsView reads ?account=… from the URL, so it renders below a Suspense boundary.
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <OperationsView />
    </Suspense>
  );
}

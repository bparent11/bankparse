import type { Metadata } from "next";

import { FilesView } from "./files-view";

export const metadata: Metadata = { title: "Fichiers" };

export default function FilesPage() {
  return <FilesView />;
}

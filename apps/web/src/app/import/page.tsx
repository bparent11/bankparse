import type { Metadata } from "next";

import { PageHeader } from "@/components/common";

import { Uploader } from "./uploader";

export const metadata: Metadata = { title: "Importer" };

export default function ImportPage() {
  return (
    <>
      <PageHeader
        title="Importer des relevés"
        description="Déposez vos relevés PDF Crédit Agricole, Crédit Mutuel ou Boursorama. Les opérations déjà connues sont ignorées automatiquement."
      />
      <Uploader />
    </>
  );
}

import type { DocStatus, DocType } from "./api/client";

export const DOC_TYPES: Record<DocType, string> = {
  bilan_bio: "Bilan biologique",
  efr: "EFR",
  compte_rendu: "Compte rendu",
  ordonnance: "Ordonnance",
  radiographie: "Radiographie",
  inconnu: "Type à préciser",
};

export const DOC_STATUS: Record<DocStatus, { label: string; tone: string }> = {
  uploaded: { label: "En file d'attente", tone: "bg-paper text-ink-2" },
  processing: { label: "Lecture en cours", tone: "bg-info-soft text-info" },
  extracted: { label: "À valider", tone: "bg-warn-soft text-warn" },
  validated: { label: "Validé", tone: "bg-ok-soft text-ok" },
  failed: { label: "Échec de lecture", tone: "bg-alert-soft text-alert" },
};

/** Explication en clair des signalements posés par l'extraction. */
export const FLAGS: Record<string, string> = {
  ocr: "Lu sur un scan ou une photo",
  ocr_digit_fix: "Caractère douteux interprété comme un chiffre",
  unit_fuzzy: "Unité mal lue, rapprochée de l'unité la plus proche",
  unit_inferred: "Unité absente, déduite de l'ordre de grandeur",
  unit_unknown: "Unité introuvable",
  implausible: "Valeur hors des bornes plausibles",
  label_fuzzy: "Libellé mal lu, rapproché du paramètre le plus proche",
  columns_inferred: "Colonnes du tableau déduites (en-tête illisible)",
  llm: "Extrait par le LLM local",
};

export const DATE_SOURCE: Record<string, string> = {
  user: "saisie au dépôt",
  detected: "lue dans le document",
  upload: "date de dépôt (à vérifier)",
};

export function fmtDate(iso: string | null | undefined): string {
  return iso ? new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString("fr-FR") : "Non renseignée";
}

export function fmtNum(v: number, unit?: string): string {
  const s = v.toLocaleString("fr-FR", { maximumFractionDigits: unit === "ratio" ? 2 : 3 });
  return unit && unit !== "ratio" && unit !== "pH" ? `${s} ${unit}` : s;
}

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

export const EVENT_TYPES: Record<string, string> = {
  exacerbation: "Exacerbation",
  hospitalisation: "Hospitalisation",
  pneumonie: "Pneumonie",
  treatment_change: "Changement de traitement",
  autre: "Autre événement",
};

export const TREND: Record<string, { label: string; tone: string }> = {
  improving: { label: "Amélioration", tone: "bg-ok-soft text-ok" },
  worsening: { label: "Dégradation", tone: "bg-alert-soft text-alert" },
  stable: { label: "Stable", tone: "bg-paper text-ink-2" },
  insufficient: { label: "Moins de 3 mesures", tone: "bg-paper text-ink-3" },
};

/** Paramètres affichés par défaut selon la pathologie suivie. */
export const DEFAULT_PARAMS: Record<string, string[]> = {
  bpco: ["FEV1", "FEV1_FVC", "SPO2", "CRP", "EOS"],
  fibrose: ["FVC_PRED", "DLCO_PRED", "SPO2", "CRP"],
  pneumonie: ["CRP", "WBC", "PCT", "SPO2"],
};

export function fmtValue(v: number, unit: string): string {
  const digits = Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
  const s = v.toLocaleString("fr-FR", { maximumFractionDigits: digits });
  return unit === "ratio" || unit === "pH" ? s : s;
}

export function unitLabel(unit: string): string {
  return unit === "ratio" || unit === "pH" ? "" : unit;
}

export const PATHOLOGIES: Record<string, string> = {
  Consolidation: "Consolidation",
  Pneumonia: "Pneumonie",
  "Lung Opacity": "Opacité pulmonaire",
  Infiltration: "Infiltrat",
  Effusion: "Épanchement pleural",
  Atelectasis: "Atélectasie",
  Emphysema: "Emphysème",
  Fibrosis: "Fibrose",
  Edema: "Œdème",
  Cardiomegaly: "Cardiomégalie",
};

/** Score IA suivi par défaut selon la pathologie du patient. */
export const DEFAULT_SCORE: Record<string, string> = { bpco: "Emphysema", fibrose: "Fibrosis", pneumonie: "Consolidation" };

export const QUALITY: Record<string, string> = {
  couleur: "Image en couleur (une radiographie est en niveaux de gris)",
  resolution_faible: "Résolution faible",
  proportions_inhabituelles: "Proportions inhabituelles (recadrage ou vue de profil ?)",
  contraste_faible: "Contraste faible",
};

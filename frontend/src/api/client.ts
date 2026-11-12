/**
 * Client HTTP de l'API MediMind.
 * Le jeton d'accès vit en mémoire uniquement ; le jeton de rafraîchissement est un cookie httpOnly
 * (invisible du JavaScript). Sur une réponse 401, une seule tentative de rafraîchissement est faite.
 */

export type FieldError = { field: string; message: string };

export class ApiError extends Error {
  status: number;
  errors: FieldError[];
  constructor(status: number, message: string, errors: FieldError[] = []) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

let accessToken: string | null = null;
let onSessionLost: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function setSessionLostHandler(handler: () => void) {
  onSessionLost = handler;
}

type TokenResponse = { access_token: string; expires_in: number };

export async function refreshSession(): Promise<boolean> {
  const r = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
  if (!r.ok) {
    accessToken = null;
    return false;
  }
  accessToken = ((await r.json()) as TokenResponse).access_token;
  return true;
}

async function toError(r: Response): Promise<ApiError> {
  let body: { detail?: unknown; errors?: FieldError[] } = {};
  try {
    body = await r.json();
  } catch {
    /* corps non JSON */
  }
  const message = typeof body.detail === "string" ? body.detail : `Erreur ${r.status}`;
  return new ApiError(r.status, message, body.errors ?? []);
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const r = await fetch(`/api${path}`, { ...init, headers, credentials: "same-origin" });
  if (r.status === 401 && retry && path !== "/auth/login") {
    if (await refreshSession()) return api<T>(path, init, false);
    onSessionLost?.();
  }
  if (!r.ok) throw await toError(r);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body: JSON.stringify(body) });

// ---------------------------------------------------------------- types partagés
export type Role = "doctor" | "admin";
export type User = { id: string; name: string; email: string; role: Role; is_active: boolean };
export type Patient = {
  id: string;
  first_name: string;
  last_name: string;
  birth_date: string;
  age: number;
  sex: "M" | "F";
  height_cm: number | null;
  antecedents: string | null;
  pack_years: number | null;
  allergies: string | null;
  base_treatments: string | null;
  conditions: string[];
};
export type Health = {
  status: string;
  database: string;
  ollama: string;
  ollama_model: string;
  imaging_model: string;
  referential_version: string;
};

export async function login(email: string, password: string): Promise<void> {
  const t = await post<TokenResponse>("/auth/login", { email, password });
  accessToken = t.access_token;
}

export async function logout(): Promise<void> {
  await api<void>("/auth/logout", { method: "POST" }, false).catch(() => undefined);
  accessToken = null;
}

// ---------------------------------------------------------------- documents et mesures
export type DocType = "bilan_bio" | "efr" | "compte_rendu" | "ordonnance" | "radiographie" | "inconnu";
export type DocStatus = "uploaded" | "processing" | "extracted" | "validated" | "failed";
export type MedDocument = {
  id: string;
  patient_id: string;
  type: DocType;
  type_confidence: number | null;
  type_source: string | null;
  exam_date: string | null;
  date_source: string | null;
  original_name: string;
  mime_type: string;
  status: DocStatus;
  confidence: number | null;
  page_count: number | null;
  warnings: string[] | null;
  processing_seconds: number | null;
  created_at: string;
  pending_count: number;
  validated_count: number;
};
export type Bbox = { page: number; x0: number; y0: number; x1: number; y1: number };
export type ValidationStatus = "pending" | "validated" | "corrected" | "rejected" | "suspect";
export type Measurement = {
  id: string;
  parameter_code: string;
  value: number;
  unit: string;
  date: string;
  context: string[];
  source_document_id: string | null;
  source_text: string | null;
  printed_value: number | null;
  printed_unit: string | null;
  flags: string[];
  bbox: Bbox | null;
  confidence: number | null;
  validation_status: ValidationStatus;
  validated_at: string | null;
};
export type UploadResult = {
  filename: string;
  status: "queued" | "duplicate" | "rejected";
  message: string | null;
  document_id: string | null;
  job_id: string | null;
};
export type ParameterDef = { code: string; name: string; unit: string; category: string };
export type Referential = {
  version: string;
  contexts: Record<string, string>;
  conditions: Record<string, string>;
  parameters: ParameterDef[];
};

export function uploadDocuments(patientId: string, files: File[], examDate?: string, docType?: string) {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  if (examDate) fd.append("exam_date", examDate);
  if (docType) fd.append("doc_type", docType);
  return api<UploadResult[]>(`/patients/${patientId}/documents`, { method: "POST", body: fd });
}

/** Image d'aperçu d'une page : récupérée avec le jeton puis convertie en URL locale. */
export async function fetchPageUrl(documentId: string, page: number, width = 1000): Promise<string> {
  const headers = new Headers();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  let r = await fetch(`/api/documents/${documentId}/pages/${page}?width=${width}`, { headers });
  if (r.status === 401 && (await refreshSession())) {
    headers.set("Authorization", `Bearer ${accessToken}`);
    r = await fetch(`/api/documents/${documentId}/pages/${page}?width=${width}`, { headers });
  }
  if (!r.ok) throw new ApiError(r.status, "Aperçu indisponible");
  return URL.createObjectURL(await r.blob());
}

// ---------------------------------------------------------------- évolution
export type SeriesPoint = { id: string; date: string; value: number; context: string[]; document_id: string | null; status: string };
export type Series = {
  code: string;
  name: string;
  unit: string;
  category: string;
  reference: { low: number | null; high: number | null; note?: string | null } | null;
  points: SeriesPoint[];
  pending: SeriesPoint[];
};
export type Trend = {
  param: string;
  n: number;
  unit: string;
  qualification: "improving" | "worsening" | "stable" | "insufficient";
  slope_per_year?: number;
  change?: number;
  delta_abs?: number;
};
export type TimelineBar = {
  molecule: string;
  drug_class: string | null;
  dosage: string | null;
  start: string;
  end: string | null;
  long_term: boolean;
  documents: string[];
};
export type ClinicalEvent = { id: string; type: string; date: string; end_date: string | null; note: string | null; document_id: string | null };
export type Timeline = {
  treatments: TimelineBar[];
  treatment_changes: { date: string; added: string[]; stopped: string[] }[];
  events: ClinicalEvent[];
  radiographs: { document_id: string; date: string; name: string }[];
};
export type AlertItem = {
  id: string;
  rule_id: string;
  label: string;
  severity: "warning" | "info";
  source: string | null;
  note: string | null;
  date: string;
  current: boolean;
  state: "open" | "acknowledged";
  message: string;
  values: { date: string; value: number; unit: string; document_id: string | null }[];
  ruleset_version: string;
};
export type ExtractedTreatment = {
  id: string;
  molecule: string;
  drug_class: string | null;
  dosage: string | null;
  start_date: string;
  end_date: string | null;
  duration_days: number | null;
  confidence: number | null;
  bbox: Bbox | null;
  source_text: string | null;
  flags: string[];
  validation_status: ValidationStatus;
};
export type ExtractedEvent = {
  id: string;
  type: string;
  date: string;
  end_date: string | null;
  note: string | null;
  confidence: number | null;
  bbox: Bbox | null;
  validation_status: ValidationStatus;
  manual: boolean;
};

// ---------------------------------------------------------------- imagerie
export type ImagingItem = {
  document_id: string;
  imaging_id: string | null;
  date: string | null;
  name: string;
  analyzed: boolean;
  scores: Record<string, number> | null;
  uncertainty: Record<string, number> | null;
  quality_flags: string[];
  view: "face" | "profil" | null;
  model_name: string | null;
  model_version: string | null;
  doctor_assessment: string | null;
};
export type ImagingList = { pathologies: string[]; model_name: string; items: ImagingItem[] };

/** Ressource binaire protégée (image, carte) récupérée avec le jeton puis convertie en URL locale. */
export async function fetchBlobUrl(path: string): Promise<string> {
  const headers = new Headers();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  let r = await fetch(`/api${path}`, { headers });
  if (r.status === 401 && (await refreshSession())) {
    headers.set("Authorization", `Bearer ${accessToken}`);
    r = await fetch(`/api${path}`, { headers });
  }
  if (!r.ok) throw new ApiError(r.status, "Image indisponible");
  return URL.createObjectURL(await r.blob());
}

// ---------------------------------------------------------------- fiche pré-consultation
export type Sheet = { id: string; created_at: string; mode: "template" | "llm"; html: string; pages: number; as_of: string };

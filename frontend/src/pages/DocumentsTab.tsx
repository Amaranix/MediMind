import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, uploadDocuments, type MedDocument, type UploadResult } from "../api/client";
import { DOC_STATUS, DOC_TYPES, fmtDate } from "../labels";

const ACCEPT = "application/pdf,image/jpeg,image/png";

function Uploader({ patientId }: { patientId: string }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [examDate, setExamDate] = useState("");
  const [docType, setDocType] = useState("");
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [results, setResults] = useState<UploadResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function add(list: FileList | null) {
    if (list) setFiles((prev) => [...prev, ...Array.from(list)]);
  }
  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    add(e.dataTransfer.files);
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResults(await uploadDocuments(patientId, files, examDate || undefined, docType || undefined));
      setFiles([]);
      if (input.current) input.current.value = "";
      qc.invalidateQueries({ queryKey: ["documents", patientId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dépôt impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="panel mb-6 p-5" aria-label="Déposer des documents">
      <h2 className="mb-3 text-lg font-bold">Déposer des documents</h2>
      <label
        htmlFor="files"
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-7 text-center
          ${over ? "border-teal bg-teal-soft" : "border-grid-strong bg-paper"}`}
      >
        <span className="font-semibold">Glissez des fichiers ici ou cliquez pour les choisir</span>
        <span className="text-sm text-ink-2">Bilans, EFR, comptes rendus, ordonnances, radiographies : PDF, JPG ou PNG, 25 Mo maximum</span>
        <input id="files" ref={input} type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => add(e.target.files)} />
      </label>
      {files.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2 text-sm">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center gap-2 rounded border border-grid bg-paper px-2 py-1">
              {f.name}
              <button type="button" className="text-ink-3 hover:text-alert" aria-label={`Retirer ${f.name}`}
                onClick={() => setFiles(files.filter((_, k) => k !== i))}>×</button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-[200px_220px_auto] lg:items-end">
        <div>
          <label htmlFor="exam-date" className="label">Date de l'examen (facultatif)</label>
          <input id="exam-date" type="date" className="field" value={examDate} max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setExamDate(e.target.value)} />
        </div>
        <div>
          <label htmlFor="doc-type" className="label">Type (facultatif)</label>
          <select id="doc-type" className="field" value={docType} onChange={(e) => setDocType(e.target.value)}>
            <option value="">Détection automatique</option>
            {Object.entries(DOC_TYPES).filter(([k]) => k !== "inconnu").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <button type="submit" className="btn btn-primary h-[38px]" disabled={busy || files.length === 0}>
          {busy ? "Dépôt en cours…" : files.length > 1 ? `Déposer ${files.length} fichiers` : "Déposer"}
        </button>
      </div>
      <p className="mt-2 text-sm text-ink-3">Sans date saisie, la date est lue dans le document. La date et le type restent modifiables ensuite.</p>
      {error && <p role="alert" className="mt-3 text-sm text-alert">{error}</p>}
      {results && (
        <ul className="mt-3 space-y-1 text-sm" aria-live="polite">
          {results.map((r, i) => (
            <li key={i} className={r.status === "queued" ? "text-ok" : r.status === "duplicate" ? "text-warn" : "text-alert"}>
              <b>{r.filename}</b> : {r.status === "queued" ? "déposé, lecture en cours" : r.message}
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}

export function DocumentsTab() {
  const { patientId = "" } = useParams();
  const qc = useQueryClient();
  const { data: docs } = useQuery({
    queryKey: ["documents", patientId],
    queryFn: () => api<MedDocument[]>(`/patients/${patientId}/documents`),
    refetchInterval: (q) => {
      const busy = q.state.data?.some((d) => d.status === "uploaded" || d.status === "processing");
      if (!busy && q.state.data) qc.invalidateQueries({ queryKey: ["pending", patientId] });
      return busy ? 2000 : false;
    },
  });

  return (
    <>
      <Uploader patientId={patientId} />
      <h2 className="mb-3 text-lg font-bold">Documents du dossier</h2>
      {docs && docs.length === 0 && (
        <p className="panel p-6 text-ink-2">Aucun document pour l'instant. Déposez les bilans, EFR et comptes rendus du patient pour reconstituer son historique.</p>
      )}
      {docs && docs.length > 0 && (
        <div className="panel overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-paper text-sm text-ink-2">
              <tr>
                <th className="px-4 py-3 font-semibold">Date d'examen</th>
                <th className="px-4 py-3 font-semibold">Type</th>
                <th className="px-4 py-3 font-semibold">Fichier</th>
                <th className="px-4 py-3 font-semibold">État</th>
                <th className="px-4 py-3 font-semibold">Valeurs</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => {
                const st = DOC_STATUS[d.status];
                return (
                  <tr key={d.id} className="border-t border-grid">
                    <td className="px-4 py-3 whitespace-nowrap">
                      {fmtDate(d.exam_date)}
                      {d.date_source === "upload" && <span className="block text-xs text-warn">à vérifier</span>}
                    </td>
                    <td className="px-4 py-3">{DOC_TYPES[d.type]}</td>
                    <td className="max-w-[260px] truncate px-4 py-3 text-ink-2" title={d.original_name}>{d.original_name}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded px-2 py-0.5 text-[13px] font-semibold ${st.tone}`}>{st.label}</span>
                      {!!d.warnings?.length && <span className="ml-2 text-xs text-warn">{d.warnings.length} remarque(s)</span>}
                    </td>
                    <td className="px-4 py-3 text-sm whitespace-nowrap">
                      {d.pending_count > 0 && <span className="block font-semibold text-warn">{d.pending_count} à valider</span>}
                      {d.validated_count > 0 && <span className="block text-ok">{d.validated_count} validée(s)</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {d.status !== "uploaded" && d.status !== "processing" && (
                        <Link className="btn" to={`/patients/${patientId}/documents/${d.id}`}>
                          {d.pending_count > 0 ? "Valider" : "Ouvrir"}
                        </Link>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

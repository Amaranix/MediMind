import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type MedDocument } from "../api/client";
import { DOC_TYPES, fmtDate } from "../labels";

/** Documents dont au moins une valeur attend la décision du médecin. */
export function PendingTab() {
  const { patientId = "" } = useParams();
  const { data: docs } = useQuery({
    queryKey: ["documents", patientId],
    queryFn: () => api<MedDocument[]>(`/patients/${patientId}/documents`),
  });
  const todo = (docs ?? []).filter((d) => d.pending_count > 0 || d.type === "inconnu");
  if (!docs) return <p className="text-ink-2">Chargement…</p>;
  if (todo.length === 0)
    return <p className="panel p-6 text-ink-2">Rien à valider : toutes les valeurs extraites ont reçu une décision.</p>;
  return (
    <ul className="space-y-3">
      {todo.map((d) => (
        <li key={d.id} className="panel flex flex-wrap items-center justify-between gap-3 p-4">
          <div>
            <div className="font-semibold">{DOC_TYPES[d.type]} du {fmtDate(d.exam_date)}</div>
            <div className="text-sm text-ink-2">{d.original_name}</div>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-semibold text-warn">{d.pending_count} valeur(s) à valider</span>
            <Link className="btn btn-primary" to={`/patients/${patientId}/documents/${d.id}`}>Valider</Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { fetchBlobUrl, post, type Sheet } from "../api/client";
import { usePending } from "./PatientPage";

/** Fiche pré-consultation (F-E1) : générée par gabarit à partir des seules données validées, aperçu et PDF. */
export function SheetTab() {
  const { patientId = "" } = useParams();
  const { data: pending } = usePending(patientId);
  const [assisted, setAssisted] = useState(false);
  const gen = useMutation({ mutationFn: () => post<Sheet>(`/patients/${patientId}/sheets?assisted=${assisted}`) });
  const download = useMutation({
    mutationFn: async (id: string) => {
      const url = await fetchBlobUrl(`/sheets/${id}/pdf`);
      const a = Object.assign(document.createElement("a"), { href: url, download: "fiche-pre-consultation.pdf" });
      a.click();
      URL.revokeObjectURL(url);
    },
  });
  const s = gen.data;
  return (
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_260px]">
      <div className="min-w-0">
        {s ? (
          // Aperçu isolé : sandbox sans script, contenu échappé côté serveur
          <iframe title="Aperçu de la fiche pré-consultation" sandbox="" srcDoc={s.html}
            className="h-[1123px] w-full max-w-[794px] border border-grid-strong bg-white" />
        ) : (
          <p className="text-ink-2">
            La fiche résume le dossier sur une page A4 : motif, évolution, alertes, radiographies comparées, traitements
            et points à aborder. Chaque chiffre renvoie à son document source.
          </p>
        )}
        {gen.error && <p role="alert" className="mt-2 text-alert">{gen.error.message}</p>}
      </div>
      <aside className="rounded-m border border-grid bg-surface p-4" aria-label="Contrôle de la fiche">
        <h2 className="mb-2 text-[15px] font-bold">Contrôle</h2>
        {s?.mode === "llm" ? (
          <p className="text-sm">
            Synthèse rédigée par le LLM local : {s.attempts.at(-1)?.checked} nombres et dates vérifiés, tous présents
            dans les données validées ({s.attempts.length} essai{s.attempts.length > 1 ? "s" : ""}, {s.seconds} s).
          </p>
        ) : s?.assisted ? (
          <p className="text-sm text-warn">
            Rédaction assistée indisponible ({s.attempts.length} essai(s) refusé(s) par le vérificateur, {s.seconds} s) :
            fiche par gabarit.
          </p>
        ) : (
          <p className="text-sm">Rédaction par gabarit : résultat identique à chaque génération.</p>
        )}
        {s?.attempts.some((a) => !a.ok) && (
          <details className="mt-1 text-[12.5px] text-ink-2">
            <summary>Erreurs relevées par le vérificateur</summary>
            <ul className="mt-1 list-disc pl-4">
              {s.attempts.flatMap((a) => a.issues).map((i, k) => <li key={k}>{i}</li>)}
            </ul>
          </details>
        )}
        {s && <p className="mt-1 text-sm">{s.pages === 1 ? "Tient sur une page." : `${s.pages} pages : la fiche dépasse une page.`}</p>}
        {!!pending?.measurements && (
          <p className="mt-1 text-sm text-warn">
            {pending.measurements} valeur(s) à valider : elles ne figurent pas dans la fiche.
          </p>
        )}
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={assisted} onChange={(e) => setAssisted(e.target.checked)} />
          Rédaction assistée (LLM local, expérimental)
        </label>
        {assisted && <p className="text-[12.5px] text-ink-2">Jusqu'à 2 minutes sur ce poste. Chaque nombre et chaque date sont vérifiés.</p>}
        <button type="button" className="btn btn-primary mt-3 w-full" onClick={() => gen.mutate()} disabled={gen.isPending}>
          {gen.isPending ? "Génération…" : s ? "Régénérer" : "Générer la fiche"}
        </button>
        {s && (
          <button type="button" className="btn mt-2 w-full" onClick={() => download.mutate(s.id)} disabled={download.isPending}>
            Télécharger le PDF
          </button>
        )}
        {download.error && <p role="alert" className="mt-2 text-sm text-alert">{download.error.message}</p>}
      </aside>
    </div>
  );
}

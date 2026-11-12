import { useMutation } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { fetchBlobUrl, post, type Sheet } from "../api/client";
import { usePending } from "./PatientPage";

/** Fiche pré-consultation (F-E1) : générée par gabarit à partir des seules données validées, aperçu et PDF. */
export function SheetTab() {
  const { patientId = "" } = useParams();
  const { data: pending } = usePending(patientId);
  const gen = useMutation({ mutationFn: () => post<Sheet>(`/patients/${patientId}/sheets`) });
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
        <p className="text-sm">Rédaction par gabarit : résultat identique à chaque génération.</p>
        {s && <p className="mt-1 text-sm">{s.pages === 1 ? "Tient sur une page." : `${s.pages} pages : la fiche dépasse une page.`}</p>}
        {!!pending?.measurements && (
          <p className="mt-1 text-sm text-warn">
            {pending.measurements} valeur(s) à valider : elles ne figurent pas dans la fiche.
          </p>
        )}
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

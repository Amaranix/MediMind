import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, post, type AssistantMessage } from "../api/client";
import { fmtDate } from "../labels";

/*
 * Assistant du dossier (F-E4). Les réponses sont lues dans les données validées et mises en forme par le code
 * (aucune phrase rédigée par un LLM) ; chaque réponse cite ses documents. Pas de diagnostic ni de prescription.
 */
const EXAMPLES = [
  "Quelle est la dernière valeur de la CRP ?",
  "Combien d'exacerbations le patient a-t-il présentées ?",
  "De combien le VEMS a-t-il varié entre le 20/11/2025 et le 05/11/2026 ?",
  "Quels sont les traitements de fond en cours ?",
];

function Message({ m, patientId }: { m: AssistantMessage; patientId: string }) {
  const tone = m.kind === "refusal" ? "border-warn bg-warn-soft" : m.kind === "not_found" ? "border-grid-strong bg-paper" : "border-teal bg-surface";
  return (
    <li className="space-y-1.5">
      <p className="ml-auto w-fit max-w-[80%] rounded-lg bg-teal-soft px-3 py-2 text-sm">{m.question}</p>
      <div className={`max-w-[90%] rounded-lg border-l-[3px] px-3 py-2 text-sm ${tone}`}>
        <p>{m.text}</p>
        {m.passages.length > 0 && (
          <ul className="mt-2 space-y-2">
            {m.passages.map((p, i) => (
              <li key={i} className="rounded border border-grid bg-paper p-2">
                <div className="mb-1 text-[12.5px] text-ink-2">
                  <Link className="text-teal-ink underline" to={`/patients/${patientId}/documents/${p.document_id}`}>{p.type} du {fmtDate(p.date)}</Link>
                  {" "}· proximité {p.score.toLocaleString("fr-FR")}
                </div>
                <p className="whitespace-pre-line text-[13px]">{p.text}</p>
              </li>
            ))}
          </ul>
        )}
        {m.citations.length > 0 && (
          <p className="mt-1.5 text-[12.5px] text-ink-2">
            Sources :{" "}
            {m.citations.map((c, i) => (
              <span key={c.document_id}>
                {i > 0 && ", "}
                <Link className="text-teal-ink underline" to={`/patients/${patientId}/documents/${c.document_id}`}>{c.type} du {fmtDate(c.date)}</Link>
              </span>
            ))}
          </p>
        )}
      </div>
    </li>
  );
}

export function AssistantTab() {
  const { patientId = "" } = useParams();
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const { data: history } = useQuery({
    queryKey: ["assistant", patientId],
    queryFn: () => api<AssistantMessage[]>(`/patients/${patientId}/assistant`),
  });
  const ask = useMutation({
    mutationFn: (q: string) => post<AssistantMessage>(`/patients/${patientId}/assistant`, { question: q }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assistant", patientId] }),
    onError: (_e, q) => setQuestion(q),  // la question n'est pas perdue en cas d'erreur
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setQuestion("");
    ask.mutate(q);
  }
  return (
    <div className="max-w-[860px]">
      <p className="mb-3 text-sm text-ink-2">
        Posez une question sur ce dossier. Les réponses sont lues dans les données validées et citent leurs documents ;
        l'assistant ne donne ni diagnostic ni prescription.
      </p>
      <ul className="mb-4 space-y-4" aria-live="polite">
        {history?.map((m, i) => <Message key={i} m={m} patientId={patientId} />)}
      </ul>
      {!history?.length && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((q) => (
            <button key={q} type="button" className="rounded-full border border-grid-strong bg-surface px-2.5 py-1 text-[13px] text-ink-2"
              onClick={() => setQuestion(q)}>{q}</button>
          ))}
        </div>
      )}
      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor="assistant-q" className="sr-only">Votre question</label>
        <input id="assistant-q" className="field" maxLength={500} value={question} onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ex. : Quelle était la CRP le 10/02/2026 ?" />
        <button type="submit" className="btn btn-primary" disabled={ask.isPending || !question.trim()}>
          {ask.isPending ? "…" : "Demander"}
        </button>
      </form>
      {ask.error && <p role="alert" className="mt-2 text-sm text-alert">{ask.error.message}</p>}
    </div>
  );
}

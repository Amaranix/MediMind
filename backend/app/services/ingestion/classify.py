"""Classification du document (F-A5) : mots-clés pondérés d'abord, LLM local seulement si les règles hésitent."""
from __future__ import annotations

from dataclasses import dataclass

from app.services.ingestion.normalize import fold
from app.services.ingestion.text import DocumentText

KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "efr": [("explorations fonctionnelles", 4), ("exploration fonctionnelle", 4), ("vems", 2), ("cvf", 2),
            ("dlco", 2), ("theorique", 1.5), ("pre bd", 2), ("post bd", 2), ("reversibilite", 2), ("spirometr", 3)],
    "bilan_bio": [("laboratoire", 2), ("prelevement", 2), ("biologiste", 3), ("leucocytes", 1.5),
                  ("hemoglobine", 1.5), ("plaquettes", 1.5), ("hematologie", 2), ("biochimie", 2),
                  ("valeurs usuelles", 2), ("normes", 1), ("analyses", 1.5), ("globules blancs", 1.5)],
    "ordonnance": [("ordonnance", 5), ("pendant", 1), ("fois par jour", 2), ("traitement au long cours", 3),
                   ("inhalation", 1), ("comprime", 1.5), ("bouffees", 1.5), ("posologie", 2)],
    "compte_rendu": [("compte rendu", 4), ("consultation", 2), ("hospitalisation", 2), ("examen clinique", 2),
                     ("auscultation", 2), ("patient", 0.5), ("dyspnee", 1), ("evolution", 1)],
}
MIN_SCORE = 4.0
MIN_MARGIN = 1.5


@dataclass
class Classification:
    type: str
    confidence: float
    method: str  # rules | llm | image
    scores: dict[str, float]


def classify_rules(doc: DocumentText) -> Classification:
    real_words = [w for w in doc.words if w.conf >= 0.6 and sum(c.isalpha() for c in w.text) >= 3]
    if doc.is_image and len(real_words) < 8:
        # Image quasi sans texte : radiographie (vérifiée ensuite par le module d'imagerie)
        return Classification("radiographie", 0.9, "image", {})
    text = fold(doc.text)
    scores = {t: sum(w for k, w in kws if k in text) for t, kws in KEYWORDS.items()}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (best, s1), (_, s2) = ranked[0], ranked[1]
    if s1 >= MIN_SCORE and s1 - s2 >= MIN_MARGIN:
        conf = min(0.99, 0.6 + 0.4 * (s1 - s2) / s1)
        return Classification(best, round(conf, 2), "rules", scores)
    return Classification("inconnu", 0.0, "rules", scores)

"""Test de bout en bout du scénario de démonstration, parcours A (docs/demo-scenario.md), dans un vrai navigateur.

Prérequis : pile lancée puis `scripts/seed_demo.py` (instance neuve : le test dépose la visite du 05/11/2026).
Usage : MEDIMIND_URL=https://localhost:8443 pytest e2e   (pip install -r e2e/requirements.txt ; playwright install chromium)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("MEDIMIND_URL", "https://localhost:8443")
EMAIL, PASSWORD = "berrada@medimind.local", "demo-pneumo-2026"
expect.set_options(timeout=60_000)  # lecture OCR, analyse des radiographies : plusieurs secondes
LIVE = sorted((ROOT / "synthetic" / "out" / "A01").rglob("2026-11-05*"))


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(ignore_https_errors=True, viewport={"width": 1400, "height": 1000})
        pg.set_default_timeout(60_000)
        yield pg
        browser.close()


def validate_all(page: Page) -> None:
    """Sur l'écran de validation : valeurs sûres d'un coup, puis chaque valeur restante une par une."""
    # le compteur « (N à décider) » n'apparaît qu'une fois les valeurs chargées
    expect(page.get_by_role("heading", name=re.compile(r"^Valeurs extraites \(\d+ à décider\)"))).to_be_visible()
    bulk = page.get_by_role("button", name=re.compile(r"^Valider les \d+ valeurs sûres$"))
    if bulk.count():
        bulk.click()
        expect(bulk).to_have_count(0)  # plus aucune valeur « sûre » : l'affichage est à jour
    buttons = page.get_by_role("button", name="Valider", exact=True)
    for _ in range(40):
        n = buttons.count()
        if not n:
            break
        with page.expect_response(lambda r: r.request.method == "PATCH" and r.ok):
            buttons.first.click()
        expect(buttons).not_to_have_count(n)  # attendre le nouvel affichage avant le clic suivant


def test_demo_scenario_parcours_a(page: Page):
    assert len(LIVE) == 4, "documents du 05/11/2026 introuvables"
    # 1. Connexion et liste des patients
    page.goto(f"{BASE}/connexion")
    page.get_by_label("Adresse e-mail").fill(EMAIL)
    page.get_by_label("Mot de passe").fill(PASSWORD)
    page.get_by_role("button", name="Se connecter").click()
    page.get_by_text("Karim").first.click()
    expect(page.get_by_text("Les résultats de l'IA ne constituent pas un diagnostic").first).to_be_visible()

    # 2. Dépôt de la visite du 05/11/2026
    page.get_by_role("link", name="Documents").click()
    page.locator("#files").set_input_files([str(p) for p in LIVE])
    page.get_by_label("Date de l'examen (facultatif)").fill("2026-11-05")  # une radiographie PNG ne porte pas de date
    page.get_by_role("button", name="Déposer 4 fichiers").click()
    expect(page.get_by_text(re.compile("2026-11-05_D031")).first).to_be_visible()

    # 3. Validation : bilan scanné du 10/02/2026 puis documents du 05/11/2026
    page.get_by_role("link", name=re.compile("^À valider")).click()
    expect(page.get_by_text(re.compile("^Lecture en cours"))).to_have_count(0, timeout=180_000)
    expect(page.get_by_text("2026-02-10_D002_bilan_bio.pdf")).to_be_visible()
    items = page.locator("li", has=page.get_by_role("link", name="Valider"))
    done = page.get_by_text("Rien à valider")
    for _ in range(10):
        expect(items.first.or_(done)).to_be_visible()  # liste chargée (sinon on compterait 0 document trop tôt)
        if done.is_visible():
            break
        items.first.get_by_role("link", name="Valider").click()
        validate_all(page)
        # attendre la liste fraîche : la version en cache s'affiche d'abord et contient encore le document traité
        with page.expect_response(lambda r: r.url.endswith("/documents") and r.request.method == "GET"):
            page.get_by_role("link", name=re.compile("^À valider")).click()
    expect(done).to_be_visible()

    # 4. Tableau de bord : dernière valeur du VEMS, alerte de déclin, radiographies comparées
    page.get_by_role("link", name="Évolution").click()
    table = page.get_by_label("Dernières valeurs")
    # « / » échappés : Playwright transmet l'expression telle quelle dans son sélecteur
    expect(table.get_by_role("row", name=re.compile(r"^VEMS .*1,5 L · 05\/11\/2026"))).to_be_visible()
    expect(page.get_by_label("Alertes").get_by_text(re.compile("Déclin du VEMS"))).to_be_visible()
    expect(page.get_by_label("Radiographies comparées").get_by_text("R5")).to_be_visible()

    # 5. Fiche pré-consultation
    page.get_by_role("button", name="Générer la fiche").click()
    expect(page.get_by_text("Tient sur une page")).to_be_visible()

    # 6. Assistant : réponse lue dans les données et citée
    page.get_by_role("link", name="Assistant").click()
    page.get_by_label("Votre question").fill("Quel était le VEMS post-bronchodilatateur le 05/11/2026 ?")
    page.get_by_role("button", name="Demander").click()
    expect(page.get_by_text("VEMS : 1,5 L le 05/11/2026.")).to_be_visible()
    expect(page.get_by_role("link", name="EFR du 05/11/2026").first).to_be_visible()

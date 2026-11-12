/**
 * F-B7 : export du graphique d'évolution. Chaque ligne du panneau (libellé + courbe SVG) est redessinée sur un
 * canevas : PNG téléchargé, ou page d'impression (« Enregistrer en PDF » du navigateur), sans dépendance.
 */
const LABEL_W = 220;
const FONT = "Atkinson Hyperlegible Next, Arial, sans-serif";

function svgImage(svg: SVGSVGElement): Promise<HTMLImageElement> {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("style", `font-family:${FONT};font-size:12px`);
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }));
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = reject;
    img.src = url;
  });
}

/** Rendu du panneau en canevas (échelle 2 pour la netteté). */
export async function renderChart(panel: HTMLElement, title: string): Promise<HTMLCanvasElement> {
  const rows = [...panel.querySelectorAll<HTMLElement>(":scope > div.grid")].filter((r) => r.querySelector("svg"));
  const imgs = await Promise.all(rows.map((r) => svgImage(r.querySelector("svg")!)));
  const width = LABEL_W + Math.max(...imgs.map((i) => i.width));
  const header = 56;
  const height = header + imgs.reduce((h, i) => h + i.height, 0) + 28;
  const canvas = document.createElement("canvas");
  canvas.width = width * 2;
  canvas.height = height * 2;
  const g = canvas.getContext("2d")!;
  g.scale(2, 2);
  g.fillStyle = "#fff";
  g.fillRect(0, 0, width, height);
  g.fillStyle = "#1D2A31";
  g.font = `bold 16px ${FONT}`;
  g.fillText(title, 12, 22);
  g.font = `12px ${FONT}`;
  g.fillStyle = "#4A5A61";
  g.fillText("Aide à la décision, données validées par le médecin. Les scores IA sont indicatifs, non diagnostiques.", 12, 42);
  let y = header;
  rows.forEach((row, k) => {
    const lines = (row.firstElementChild as HTMLElement).innerText.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 4);
    g.fillStyle = "#1D2A31";
    lines.forEach((l, j) => {
      const isValue = j === 1 && /^[−\-–\d]/.test(l);  // 2e ligne = valeur (pas pour la frise)
      g.font = isValue ? `bold 18px ${FONT}` : j === 0 ? `bold 13px ${FONT}` : `12px ${FONT}`;
      g.fillText(l, 12, y + 18 + j * 19, LABEL_W - 20);
    });
    g.drawImage(imgs[k], LABEL_W, y);
    g.strokeStyle = "#DCE6E3";
    g.beginPath(); g.moveTo(0, y + imgs[k].height); g.lineTo(width, y + imgs[k].height); g.stroke();
    y += imgs[k].height;
  });
  g.fillStyle = "#7A8A91";
  g.fillText(`MediMind, exporté le ${new Date().toLocaleString("fr-FR")}. Démonstrateur de recherche, non dispositif médical.`, 12, y + 18);
  return canvas;
}

export async function exportPng(panel: HTMLElement, title: string, filename: string) {
  const canvas = await renderChart(panel, title);
  const a = Object.assign(document.createElement("a"), { href: canvas.toDataURL("image/png"), download: filename });
  a.click();
}

export async function exportPdf(panel: HTMLElement, title: string) {
  const canvas = await renderChart(panel, title);
  const w = window.open("", "_blank");
  if (!w) throw new Error("Fenêtre bloquée par le navigateur : autorisez les fenêtres pour imprimer.");
  w.document.title = title;
  const img = w.document.createElement("img");
  img.src = canvas.toDataURL("image/png");
  img.style.width = "100%";
  const style = w.document.createElement("style");
  style.textContent = "@page { size: A4 landscape; margin: 10mm } body { margin: 0 }";
  w.document.head.appendChild(style);
  w.document.body.appendChild(img);
  img.onload = () => { w.focus(); w.print(); };
}

/**
 * La cascada de una respuesta [[matrix]], sin React: recibe la caja y el lienzo y devuelve
 * cómo pararla. Separada del componente para poder verla en un navegador sin montar Helios.
 */
const GLIFOS = "ｦｱｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789";
const CELDA = 14;
const glifo = () => GLIFOS[Math.floor(Math.random() * GLIFOS.length)];

// El 26B, en cuanto la usó una vez, puso la marca en 7 de 9 respuestas: se veía a sí mismo
// usándola y la repetía. El efecto es un golpe, no un estilo: se concede si la persona lo
// nombra en ese mensaje o si han pasado ESPERA turnos desde la última cascada.
const ESPERA = 6;
const concedido = new Map<number, boolean>();
let ultima = -Infinity;
export function matrixAllowed(turnId: number, userText: string): boolean {
  const ya = concedido.get(turnId);
  if (ya !== undefined) return ya;
  const vale = /matrix/i.test(userText) || turnId - ultima >= ESPERA;
  if (vale) ultima = turnId;
  concedido.set(turnId, vale);
  return vale;
}

export function runMatrix(box: HTMLElement, canvas: HTMLCanvasElement, live: boolean, onDone: () => void): () => void {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      box.classList.add("matrix-done");
      if (!live) onDone();
      return () => {};
    }
    // Cada letra en su propio span, oculta, para poder soltarlas una a una. Los espacios
    // se quedan como texto: los saltos de línea caen donde caían.
    const letras: { nodo: HTMLElement; x: number; y: number }[] = [];
    if (!live) {
      const paseo = document.createTreeWalker(box.querySelector(".matrix-text")!, NodeFilter.SHOW_TEXT);
      const textos: Text[] = [];
      while (paseo.nextNode()) textos.push(paseo.currentNode as Text);
      for (const nodo of textos) {
        const trozo = document.createDocumentFragment();
        for (const letra of Array.from(nodo.data)) {
          if (/\s/.test(letra)) { trozo.append(letra); continue; }
          const span = document.createElement("span");
          span.className = "matrix-letter";
          span.textContent = letra;
          trozo.append(span);
          letras.push({ nodo: span, x: 0, y: 0 });
        }
        nodo.replaceWith(trozo);
      }
      box.classList.add("matrix-ready");
    }
    const marco = box.getBoundingClientRect();
    const ancho = Math.max(1, Math.round(marco.width)), alto = Math.max(live ? 96 : 1, Math.round(marco.height));
    for (const letra of letras) {
      const r = letra.nodo.getBoundingClientRect();
      letra.x = r.left - marco.left + r.width / 2;
      letra.y = r.top - marco.top + r.height / 2;
    }
    const dpr = window.devicePixelRatio || 1;
    canvas.width = ancho * dpr; canvas.height = alto * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);
    ctx.font = `${CELDA}px monospace`;
    ctx.textAlign = "center";
    const columnas = Math.ceil(ancho / CELDA);
    // Cada columna, sus letras de arriba abajo y una gota que sale con un retraso propio.
    const porColumna: (typeof letras)[] = Array.from({ length: columnas }, () => []);
    for (const letra of letras) porColumna[Math.min(columnas - 1, Math.floor(letra.x / CELDA))].push(letra);
    porColumna.forEach(columna => columna.sort((a, b) => a.y - b.y));
    // Que dé tiempo a verlo: una respuesta de dos líneas tarda ~2,5 s; una larga, ~3,5 s.
    const velocidad = Math.max(110, alto / 2.2);
    const gotas = porColumna.map(() => ({ y: -Math.random() * (live ? alto : Math.min(alto, 180)), suelta: 0 }));
    let anterior = performance.now(), cuadro = 0, vivo = true;
    function pintar(ahora: number) {
      if (!vivo) return;
      const dt = Math.min(.05, (ahora - anterior) / 1000);
      anterior = ahora;
      // Se apaga el rastro sin oscurecer lo de debajo: el lienzo es transparente.
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0,0,0,.14)";
      ctx.fillRect(0, 0, ancho, alto);
      ctx.globalCompositeOperation = "source-over";
      let quedan = false;
      gotas.forEach((gota, c) => {
        const antes = gota.y;
        gota.y += velocidad * dt * (live ? .45 : 1);
        if (live && gota.y > alto + CELDA) gota.y = -Math.random() * alto * .6;
        if (gota.y <= alto + CELDA) quedan = true;
        if (Math.floor(gota.y / CELDA) !== Math.floor(antes / CELDA) && gota.y > 0) {
          ctx.fillStyle = "#d9ffe6";
          ctx.fillText(glifo(), c * CELDA + CELDA / 2, Math.floor(gota.y / CELDA) * CELDA);
          ctx.fillStyle = "#19e06a";
          ctx.fillText(glifo(), c * CELDA + CELDA / 2, (Math.floor(gota.y / CELDA) - 1) * CELDA);
        }
        const columna = porColumna[c];
        while (gota.suelta < columna.length && columna[gota.suelta].y <= gota.y) columna[gota.suelta++].nodo.classList.add("on");
      });
      if (live || quedan) { cuadro = requestAnimationFrame(pintar); return; }
      box.classList.add("matrix-done");
      onDone();
    }
    cuadro = requestAnimationFrame(pintar);
    // Con la pestaña oculta no hay fotogramas: que el texto no se quede a medias.
    const visible = () => { if (document.hidden && !live) { letras.forEach(l => l.nodo.classList.add("on")); } };
    document.addEventListener("visibilitychange", visible);
    return () => {
      vivo = false; cancelAnimationFrame(cuadro);
      document.removeEventListener("visibilitychange", visible);
    };
}

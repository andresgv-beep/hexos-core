/**
 * Los ojos del modelo sobre la página que ha escrito.
 *
 * El modelo no ejecuta lo que entrega: solo lee «sigue cayendo» o «se ve en blanco» y
 * adivina. El 13/11 el 26B retocó seis veces el código de parada de una animación que
 * nunca llegaba a parar. La vista previa ya ejecuta la página, así que se le inyecta
 * una sonda que mide hechos (errores, lienzo en blanco, si sigue moviéndose) y se los
 * manda al padre; el siguiente retoque los lleva delante.
 *
 * La página es contenido del modelo, no de fiar: lo que diga la sonda se recorta, se
 * valida campo a campo y viaja como dato medido, nunca como instrucción.
 */
export interface CanvasObservation { light: number; dark: number; moving: number }
export interface PreviewObservation {
  seconds: number;
  errors: string[];
  canvas: CanvasObservation | null;
  textLength: number;
}

const MARK = "hexos-preview-probe";

/** Va el primero en <head>: tiene que estar escuchando antes de que falle el código de la página. */
export const PROBE_SCRIPT = `<script>(function(){
var errors=[],start=Date.now();
function note(t){t=String(t).slice(0,200);if(errors.length<5&&errors.indexOf(t)<0)errors.push(t);}
addEventListener('error',function(e){note((e.message||'error')+(e.lineno?' (línea '+e.lineno+')':''));});
addEventListener('unhandledrejection',function(e){note('promesa rechazada: '+(e.reason&&e.reason.message||e.reason));});
var ce=console.error;console.error=function(){note(Array.prototype.join.call(arguments,' '));return ce.apply(console,arguments);};
var small=document.createElement('canvas');small.width=96;small.height=54;
function biggest(){var all=document.querySelectorAll('canvas'),best=null,area=0;
for(var i=0;i<all.length;i++){var a=all[i].width*all[i].height;if(a>area){area=a;best=all[i];}}return best;}
function shot(c){try{var x=small.getContext('2d',{willReadFrequently:true});x.clearRect(0,0,96,54);x.drawImage(c,0,0,96,54);
return x.getImageData(0,0,96,54).data;}catch(e){return null;}}
// Con la pestaña en segundo plano el navegador no pinta: medir entonces diría «quieto»
// de una animación que solo está en pausa. Sin fotogramas en la ventana no se informa.
function report(){var c=biggest(),a=c&&shot(c),frames=0,live=true;
(function tick(){frames++;if(live)requestAnimationFrame(tick);})();
setTimeout(function(){live=false;if(frames<3)return;var canvas=null,b=c&&a&&shot(c);
if(b){var light=0,dark=0,moving=0,n=b.length/4;
for(var i=0;i<b.length;i+=4){var l=(b[i]*3+b[i+1]*6+b[i+2])/10*(b[i+3]/255);
if(b[i+3]>200&&l>215)light++;if(l<30)dark++;
if(Math.abs(b[i]-a[i])+Math.abs(b[i+1]-a[i+1])+Math.abs(b[i+2]-a[i+2])>30)moving++;}
canvas={light:light/n,dark:dark/n,moving:moving/n};}
parent.postMessage({mark:'${MARK}',seconds:Math.round((Date.now()-start)/1000),errors:errors,canvas:canvas,
textLength:(document.body&&document.body.innerText||'').trim().length},'*');},400);}
[2,5,10,20,30,45,60].forEach(function(s){setTimeout(report,s*1000);});
})();</script>`;

const ratio = (value: unknown): number | null =>
  typeof value === "number" && value >= 0 && value <= 1 ? value : null;

/** Lo que mandó la sonda, comprobado campo a campo; null si no es suyo o viene mal. */
export function parseObservation(data: unknown): PreviewObservation | null {
  if (!data || typeof data !== "object") return null;
  const raw = data as Record<string, unknown>;
  if (raw.mark !== MARK || typeof raw.seconds !== "number" || !Array.isArray(raw.errors)) return null;
  let canvas: CanvasObservation | null = null;
  if (raw.canvas && typeof raw.canvas === "object") {
    const c = raw.canvas as Record<string, unknown>;
    const light = ratio(c.light), dark = ratio(c.dark), moving = ratio(c.moving);
    if (light !== null && dark !== null && moving !== null) canvas = { light, dark, moving };
  }
  return {
    seconds: Math.max(0, Math.min(600, Math.round(raw.seconds))),
    errors: raw.errors.filter(item => typeof item === "string").slice(0, 5)
      .map(item => (item as string).replace(/\s+/g, " ").slice(0, 200)),
    canvas,
    textLength: typeof raw.textLength === "number" ? Math.max(0, Math.round(raw.textLength)) : 0,
  };
}

const percent = (value: number) => Math.round(value * 100) + " %";

/** Los hechos en frases, para ponérselos delante al modelo. */
export function describeObservation(seen: PreviewObservation): string {
  const lines = [`Medido a los ${seen.seconds} s de abrir la página.`];
  lines.push(seen.errors.length
    ? "Errores de JavaScript: " + seen.errors.map(error => JSON.stringify(error)).join("; ") + "."
    : "Sin errores de JavaScript.");
  if (seen.canvas) {
    const { light, dark, moving } = seen.canvas;
    if (light > .6) lines.push(`El lienzo está casi todo en blanco o muy claro (${percent(light)} de su superficie): no se distingue el contenido.`);
    else if (dark > .995) lines.push("El lienzo está completamente negro: no se ha dibujado nada visible.");
    else lines.push(`El lienzo tiene ${percent(dark)} de fondo oscuro y ${percent(light)} de zonas claras.`);
    lines.push(moving > .002
      ? `La animación SIGUE en movimiento en ese momento (cambia el ${percent(Math.max(moving, .01))} del lienzo en 0,4 s): no se ha detenido.`
      : "El lienzo está quieto en ese momento: nada se mueve.");
  } else if (!seen.textLength) lines.push("La página no muestra ningún texto ni tiene un lienzo que medir.");
  return lines.join(" ");
}

// Lo último medido de cada página, por su código fuente. Una sola vista abierta a la vez.
let latest: { source: string; seen: PreviewObservation } | null = null;
export function recordObservation(source: string, seen: PreviewObservation): void { latest = { source, seen }; }
export function observationFor(source: string | undefined): PreviewObservation | null {
  return source && latest?.source === source ? latest.seen : null;
}

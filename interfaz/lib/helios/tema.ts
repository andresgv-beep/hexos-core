/** El aspecto de la interfaz: unos pocos mandos independientes que se guardan en este dispositivo.
 *  Cada uno pone un atributo `data-*` en <html> y `app/temas.css` le da valor. El primero de
 *  cada lista es el aspecto clásico y no pone atributo. Sin nada guardado se usa TEMA_INICIAL. */
export const TEMA_MANDOS = {
  fondo: { nombre: "Fondo", opciones: [
    { id: "carbon", nombre: "Carbón", muestra: "#161616" },
    { id: "negro", nombre: "Negro", muestra: "#09090a" },
    { id: "azul", nombre: "Azul noche", muestra: "#0a0d12" }] },
  lienzo: { nombre: "Lienzo", opciones: [
    { id: "textura", nombre: "Con textura" },
    { id: "liso", nombre: "Liso" }] },
  contorno: { nombre: "Contornos", opciones: [
    { id: "encendido", nombre: "Encendidos" },
    { id: "discreto", nombre: "Discretos" }] },
  forma: { nombre: "Forma", opciones: [
    { id: "redondo", nombre: "Redondeada" },
    { id: "suave", nombre: "Suave" },
    { id: "recto", nombre: "Recta" }] },
  color: { nombre: "Color", opciones: [
    { id: "oro", nombre: "Dorado", muestra: "#e8b04f" },
    { id: "cian", nombre: "Cian", muestra: "#5cc8ff" },
    { id: "verde", nombre: "Verde", muestra: "#7ddc8a" },
    { id: "hueso", nombre: "Hueso", muestra: "#e9e4da" },
    { id: "rojo", nombre: "Rojo", muestra: "#ff6b57" }] },
} as const;

export type Mando = keyof typeof TEMA_MANDOS;
export type Tema = { [M in Mando]: typeof TEMA_MANDOS[M]["opciones"][number]["id"] };
export const MANDOS = Object.keys(TEMA_MANDOS) as Mando[];

export const TEMA_BASE: Tema = { fondo: "carbon", lienzo: "textura", contorno: "encendido", forma: "redondo", color: "oro" };
/** Lo que ve un dispositivo que no ha elegido nada. Lo eligió Andrés el 18/11 en el móvil:
 *  negro, liso, contornos discretos, forma suave y color hueso. */
export const TEMA_INICIAL: Tema = { fondo: "negro", lienzo: "liso", contorno: "discreto", forma: "suave", color: "hueso" };
export const TEMA_ATAJOS: ReadonlyArray<{ nombre: string; tema: Tema }> = [
  { nombre: "Predeterminado", tema: TEMA_INICIAL },
  { nombre: "Clásico", tema: TEMA_BASE },
  { nombre: "Oscuro", tema: { ...TEMA_BASE, fondo: "negro", lienzo: "liso", contorno: "discreto", forma: "suave" } },
  { nombre: "Oscuro y seco", tema: { ...TEMA_BASE, fondo: "negro", lienzo: "liso", contorno: "discreto", forma: "recto", color: "hueso" } },
];
export const CLAVE_TEMA = "helios.tema";

const valido = (mando: Mando, valor: unknown): boolean =>
  TEMA_MANDOS[mando].opciones.some(opcion => opcion.id === valor);

/** El tema guardado. Sin nada guardado (o roto), el inicial. De uno guardado, lo que falte o no se
 *  reconozca (un mando que no existía, un tema que ya no existe) va como el clásico. */
export function leerTema(texto: string | null | undefined): Tema {
  let guardado: unknown = null;
  try { guardado = texto ? JSON.parse(texto) : null; } catch { /* un valor roto es como no tener ninguno */ }
  if (!guardado || typeof guardado !== "object" || Array.isArray(guardado)) return { ...TEMA_INICIAL };
  const tema = { ...TEMA_BASE } as Record<Mando, string>;
  for (const mando of MANDOS) {
    const valor = (guardado as Record<string, unknown>)[mando];
    if (valido(mando, valor)) tema[mando] = valor as string;
  }
  return tema as Tema;
}

export const mismoTema = (a: Tema, b: Tema): boolean => MANDOS.every(mando => a[mando] === b[mando]);

/** Lo que hace falta de la raíz del documento para ponerle un tema. */
export interface RaizTema { setAttribute(nombre: string, valor: string): unknown; removeAttribute(nombre: string): unknown }

/** Pone el tema en la raíz del documento. El valor de siempre quita el atributo en vez de ponerlo. */
export function aplicarTema(raiz: RaizTema, tema: Tema): void {
  for (const mando of MANDOS) {
    if (tema[mando] === TEMA_BASE[mando]) raiz.removeAttribute(`data-${mando}`);
    else raiz.setAttribute(`data-${mando}`, tema[mando]);
  }
}

/** Guarda el tema en este navegador. Sin almacenamiento (modo privado) el tema dura lo que la página.
 *  El inicial no se guarda: así, si un día cambia, le llega a quien no eligió otro. */
export function guardarTema(tema: Tema, almacen: Pick<Storage, "setItem" | "removeItem"> | null | undefined): void {
  try {
    if (mismoTema(tema, TEMA_INICIAL)) almacen?.removeItem(CLAVE_TEMA);
    else almacen?.setItem(CLAVE_TEMA, JSON.stringify(tema));
  } catch { /* cuota llena o almacenamiento bloqueado: no es motivo para romper Ajustes */ }
}

/** Lo mismo que leerTema + aplicarTema, en un guion que va en el <head> y corre antes de pintar:
 *  así la página no sale un instante con el tema de siempre y luego salta al guardado. */
export const GUION_TEMA = `try{var t=null;try{t=JSON.parse(localStorage.getItem(${JSON.stringify(CLAVE_TEMA)})||"null")}catch(e){}if(!t||typeof t!=="object"||Array.isArray(t))t=${
  JSON.stringify(TEMA_INICIAL)};var v=${
  JSON.stringify(Object.fromEntries(MANDOS.map(mando => [mando, TEMA_MANDOS[mando].opciones.map(opcion => opcion.id)])))
},b=${JSON.stringify(TEMA_BASE)},d=document.documentElement;for(var k in v)if(v[k].indexOf(t[k])>=0&&t[k]!==b[k])d.setAttribute("data-"+k,t[k])}catch(e){}`;

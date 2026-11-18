// El titular del chat vacío. Era siempre «Hablemos, socio.» y Andrés lo vio aburrido
// (18/11): ahora sale uno al azar entre los de esa franja del día y unos cuantos de
// siempre, con alguno propio del lunes por la mañana y del viernes por la tarde.

const MADRUGADA = ["¿Tú tampoco duermes, socio?", "A estas horas salen las mejores ideas.",
  "Las tantas y aquí seguimos.", "Silencio total. Buen momento para pensar."];
const MANANA = ["Buenos días, socio.", "Café en mano, ¿qué tenemos hoy?", "Arrancamos cuando quieras.",
  "Mañana fresca, cabeza despejada."];
const TARDE = ["Buenas tardes, socio.", "¿Qué se cuece esta tarde?", "Aquí sigo, ¿en qué andamos?",
  "Tarde de las productivas, ¿o no?"];
const NOCHE = ["Buenas noches, socio.", "¿Una última cosa antes de cerrar?", "La noche es joven, ¿qué montamos?",
  "Hora tranquila. Dispara."];
const SIEMPRE = ["Hablemos, socio.", "Tú dirás.", "¿Qué tienes en la cabeza?", "Listo cuando tú lo estés.",
  "Cuéntame, socio."];
const LUNES = ["Lunes otra vez. Vamos allá."];
const VIERNES = ["Viernes, socio. ¿Algo rápido o algo épico?"];

/** Los titulares posibles para ese momento. */
export function saludosPara(fecha: Date): string[] {
  const hora = fecha.getHours();
  const dia = fecha.getDay();
  const franja = hora < 6 ? MADRUGADA : hora < 13 ? MANANA : hora < 20 ? TARDE : NOCHE;
  const extra = dia === 1 && hora >= 6 && hora < 13 ? LUNES : dia === 5 && hora >= 13 ? VIERNES : [];
  return [...franja, ...extra, ...SIEMPRE];
}

/** Uno de ellos; `azar` en [0, 1), como Math.random(). */
export function elegirSaludo(fecha: Date, azar: number): string {
  const opciones = saludosPara(fecha);
  const i = Math.min(opciones.length - 1, Math.max(0, Math.floor(azar * opciones.length)));
  return opciones[i];
}

import { test } from "node:test";
import assert from "node:assert/strict";
import { elegirSaludo, saludosPara } from "../lib/helios/saludo";

const a = (y: number, m: number, d: number, h: number) => new Date(y, m - 1, d, h, 0);

test("cambia con la franja del día", () => {
  assert.ok(saludosPara(a(2026, 11, 18, 3)).includes("¿Tú tampoco duermes, socio?"));
  assert.ok(saludosPara(a(2026, 11, 18, 9)).includes("Buenos días, socio."));
  assert.ok(saludosPara(a(2026, 11, 18, 16)).includes("Buenas tardes, socio."));
  assert.ok(saludosPara(a(2026, 11, 18, 22)).includes("Buenas noches, socio."));
  assert.ok(!saludosPara(a(2026, 11, 18, 22)).includes("Buenos días, socio."));
});

test("lunes por la mañana y viernes por la tarde tienen el suyo", () => {
  assert.ok(saludosPara(a(2026, 11, 16, 9)).includes("Lunes otra vez. Vamos allá."));
  assert.ok(!saludosPara(a(2026, 11, 16, 16)).includes("Lunes otra vez. Vamos allá."));
  assert.ok(saludosPara(a(2026, 11, 20, 18)).some(s => s.startsWith("Viernes")));
});

test("el azar recorre todas y nunca se sale", () => {
  const fecha = a(2026, 11, 18, 16);
  const opciones = saludosPara(fecha);
  assert.equal(elegirSaludo(fecha, 0), opciones[0]);
  assert.equal(elegirSaludo(fecha, 0.999999), opciones[opciones.length - 1]);
  assert.equal(elegirSaludo(fecha, 1), opciones[opciones.length - 1]);
  assert.ok(opciones.includes("Hablemos, socio."));
});

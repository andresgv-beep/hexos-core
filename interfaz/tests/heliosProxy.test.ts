import assert from "node:assert/strict";
import test from "node:test";
import { heliosProxyOrigin } from "../lib/helios/proxy";

test("maps the local chat UI origin to HexOS while retaining cross-site protection", () => {
  for (const host of ["localhost", "127.0.0.1", "[::1]"]) {
    assert.equal(heliosProxyOrigin(`http://${host}:3000`), "http://127.0.0.1:8080");
  }
  for (const origin of ["https://example.com", "http://localhost:3001", "http://localhost:3000.evil.test", "null", undefined]) {
    assert.equal(heliosProxyOrigin(origin), origin);
  }
});

test("LAN access accepts only the explicitly configured exact origin", () => {
  const allowed = 'http://192.168.1.41:3000';
  assert.equal(heliosProxyOrigin(allowed, allowed), 'http://127.0.0.1:8080');
  for (const origin of ['http://192.168.1.42:3000', 'http://192.168.1.41:3001',
    'http://192.168.1.41:3000.evil.test', 'null', undefined])
    assert.equal(heliosProxyOrigin(origin, allowed), origin);
  assert.equal(heliosProxyOrigin(allowed, '*'), allowed);
  assert.equal(heliosProxyOrigin(allowed, allowed + '/path'), allowed);
});

test("the interface accepts exactly the host names of the declared origins", async () => {
  const { heliosAllowedHosts } = await import("../lib/helios/proxy");
  assert.deepEqual(heliosAllowedHosts("https://helios.tailb449cc.ts.net,http://192.168.1.35:3000"), ["helios.tailb449cc.ts.net", "192.168.1.35"]);
  assert.deepEqual(heliosAllowedHosts("https://user:pw@evil.example,no-es-url,https://ok.example/ruta"), []);
  assert.deepEqual(heliosAllowedHosts(""), []);
});

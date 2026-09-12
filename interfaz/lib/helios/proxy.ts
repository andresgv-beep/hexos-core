/** Only the local Helios UI may be translated to the backend's own origin.
 * Unrecognized origins remain intact so HexOS still rejects cross-site writes.
 */
export function heliosProxyOrigin(origin: string | undefined): string | undefined {
  const localOrigins = new Set([
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://[::1]:3000",
  ]);
  return origin && localOrigins.has(origin) ? "http://127.0.0.1:8080" : origin;
}

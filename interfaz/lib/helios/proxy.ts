/** Only the local Helios UI may be translated to the backend's own origin.
 * Unrecognized origins remain intact so HexOS still rejects cross-site writes.
 */
export function heliosProxyOrigin(origin: string | undefined, extraOrigins = process.env.HELIOS_UI_ORIGINS ?? ""): string | undefined {
  const localOrigins = new Set([
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://[::1]:3000",
  ]);
  // Explicit deployment origins only; never trust an arbitrary Host/Origin.
  for (const candidate of extraOrigins.split(',')) {
    try {
      const url = new URL(candidate.trim());
      if ((url.protocol === 'http:' || url.protocol === 'https:') &&
          !url.username && !url.password && candidate.trim() === url.origin)
        localOrigins.add(url.origin);
    } catch { /* Invalid configuration does not broaden access. */ }
  }
  return origin && localOrigins.has(origin) ? "http://127.0.0.1:8080" : origin;
}

/** Los nombres de host que el servidor de la interfaz acepta, además de localhost
 *  y las IP: los de los orígenes declarados en HELIOS_UI_ORIGINS (por ejemplo el
 *  https://…ts.net de Tailscale). Nunca «cualquiera». */
export function heliosAllowedHosts(extraOrigins = process.env.HELIOS_UI_ORIGINS ?? ""): string[] {
  const hosts = new Set<string>();
  for (const candidate of extraOrigins.split(',')) {
    try {
      const url = new URL(candidate.trim());
      if ((url.protocol === 'http:' || url.protocol === 'https:') && !url.username && !url.password
          && candidate.trim() === url.origin) hosts.add(url.hostname);
    } catch { /* Una entrada inválida no amplía el acceso. */ }
  }
  return [...hosts];
}

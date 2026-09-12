import vinext from "vinext";
import { defineConfig } from "vite";
import hostingConfig from "./.openai/hosting.json";
import { sites } from "./build/sites-vite-plugin";
import { attachmentPlugin } from "./server/attachments";
import { heliosProxyOrigin } from "./lib/helios/proxy";

const SITE_CREATOR_PLACEHOLDER_DATABASE_ID =
  "00000000-0000-4000-8000-000000000000";

const { d1, r2 } = hostingConfig;

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

const localBindingConfig = {
  main: "./worker/index.ts",
  compatibility_flags: ["nodejs_compat"],
  d1_databases: d1
    ? [
        {
          binding: d1,
          database_name: "site-creator-d1",
          database_id: SITE_CREATOR_PLACEHOLDER_DATABASE_ID,
        },
      ]
    : [],
  r2_buckets: r2
    ? [
        {
          binding: r2,
          bucket_name: "site-creator-r2",
        },
      ]
    : [],
};

export default defineConfig(async () => {
  // Keep Wrangler and Miniflare state project-local. These are non-secret tool
  // settings; application environment belongs in ignored `.env*` files.
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

  // Wrangler snapshots its log path while the Cloudflare plugin is imported.
  const { cloudflare } = await import("@cloudflare/vite-plugin");

  return {
    server: {
      ...(isCodexSeatbeltSandbox ? { watch: { useFsEvents: false, usePolling: true } } : {}),
      // Local interface only: forward the existing contract to the running agent.
      proxy: {
        "/api/helios": {
          target: "http://127.0.0.1:8080",
          rewrite: (path: string) => path.replace(/^\/api\/helios/, "/api"),
          configure: (proxy: Parameters<NonNullable<import("vite").ProxyOptions["configure"]>>[0]) => {
            proxy.on("proxyReq", (outgoing, incoming) => {
              const origin = heliosProxyOrigin(incoming.headers.origin);
              if (origin) outgoing.setHeader("Origin", origin);
            });
          },
        },
      },
    },
    // `three` and `three/addons` otherwise pre-bundle into two separate copies
    // of the library, so the composer's passes and the scene disagree about
    // every class identity ("Multiple instances of Three.js being imported").
    resolve: { dedupe: ["three"] },
    optimizeDeps: {
      include: [
        "three",
        "three/addons/postprocessing/EffectComposer.js",
        "three/addons/postprocessing/RenderPass.js",
        "three/addons/postprocessing/UnrealBloomPass.js",
        "three/addons/postprocessing/OutputPass.js",
      ],
    },
    plugins: [
      attachmentPlugin(),
      vinext(),
      sites(),
      cloudflare({
        viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
        config: localBindingConfig,
      }),
    ],
  };
});

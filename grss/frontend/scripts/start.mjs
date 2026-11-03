import { access, cp } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const bundle = path.join(root, ".next-build", "standalone");
const server = path.join(bundle, "server.js");
try {
  await access(server);
} catch {
  console.error("Production build missing. Run npm run build first.");
  process.exit(1);
}
await cp(path.join(root, ".next-build", "static"), path.join(bundle, ".next-build", "static"), { recursive: true });
await cp(path.join(root, "public"), path.join(bundle, "public"), { recursive: true });
process.env.PORT ??= "3000";
process.env.HOSTNAME = process.env.SENTINEL_WEB_HOST ?? "127.0.0.1";
await import(pathToFileURL(server).href);

# Sentinel Link frontend

Next.js frontend for the satellite downlink testbed. The landing page and tools share the vendored NASA Horizon Design System stylesheet, typography, and colours.

Start the API from `grss`:

```powershell
py -m sentinel serve
```

In a second terminal, from `grss/frontend`:

```powershell
npm ci
npm run dev
```

Open http://localhost:3000/attack-lab. The browser uses `/backend`, proxied by Next.js to http://127.0.0.1:8000. Set `SENTINEL_API_URL` for another upstream or `NEXT_PUBLIC_API` for a separate public API.

The Attack Lab runs a standard scenario on load. Use **Configure run** to select a recording, attack, and parameters. Up to eight completed runs remain in the sidebar while the page is open. Select a run to reopen its results.

- **Workflow:** clickable processing stages, evidence, and frame playback.
- **Frames:** spacecraft clock comparison, frame ribbon, and frame inspector.
- **Signal:** spectrogram and Doppler from the analysed audio.
- **Orbit:** the existing 3D globe, recording TLE geometry, and a pass-time slider.
- **Event stream:** frame decisions, ground truth, NASA OnAIR results, and available ledger references.

The recording upload analyser, NASA CryptoLib, trust demos, benchmark results, and documentation remain on their existing routes.

```powershell
npx tsc --noEmit
npm run build
npm start
```

Development uses `.next-dev`; production uses `.next-build`, so building does not overwrite the running development server's cache. The local reference clone under `sentinel/` is excluded from TypeScript checks and version control.

## Simulation cache

The API caches expensive analysis in memory (8 entries) and on disk (64 entries, up to 256 MiB, 7-day expiry). `SENTINEL_CACHE_DIR` changes the cache directory; the default is `grss/results/api-cache/`, which is excluded from Git. Seed, attack overrides, recording contents, model, pipeline code, and OnAIR sources identify a result. Changed inputs invalidate it automatically.

Scenario, observation, blind-sample, and OnAIR-demo results are reusable. Identical requests arriving together share one computation. Disk writes are atomic; expired or corrupt entries are recomputed. Every scenario still receives a new run ID, a capture signature made with the current station key, and new ledger entries. Timing fields describe the original analysis; `cache.status` and `cache.elapsed_ms` describe result reuse. A cache hit is labelled in the run header.

The browser shares in-flight metadata/observation requests and keeps up to 24 successful GET results for 60 seconds. Simulation POSTs, uploads, SDLS, and ledger requests always reach the server. The default proxy upstream uses IPv4 loopback to avoid Windows IPv6 fallback delays. The browser stays on the web app origin.

`npm run lint`, `npm run typecheck`, and `npm run build` check the frontend. Cache invalidation, expiry, concurrent work, persistence across restarts, and fresh signatures/audit records are covered by `grss/tests/test_cache.py`.

Full native/Compose setup and clean-install verification: [deployment guide](../deploy/README.md). `npm start` prepares and runs the standalone production bundle, including local images and fonts.

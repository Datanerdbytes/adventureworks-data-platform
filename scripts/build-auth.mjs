import { build } from "esbuild";
await build({
  entryPoints: ["auth_frontend/index.js"],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2022"],
  outfile: "my-dash-app/assets/auth.js",
  legalComments: "eof",
});

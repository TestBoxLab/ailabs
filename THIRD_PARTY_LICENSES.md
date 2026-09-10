# Third-party assets vendored in this repository

The Studio serves everything from its own origin (its Content Security Policy
allows no external scripts, styles or fonts), so these assets are copied into
`monarch-benchmark/workflowbench/wb_studio/static/vendor/`. Each folder carries
the upstream licence file. Python dependencies are declared in
`pyproject.toml` and installed by `uv`; they are not vendored.

| Asset | Version | Licence | Files | Source |
|---|---|---|---|---|
| Radix Colors | 3.0.0 | MIT | `vendor/radix-colors/radix-colors.css` (sage, gray, green, red, amber, orange, indigo, blue, plum, brown, teal; light and dark) | https://www.npmjs.com/package/@radix-ui/colors |
| IBM Plex Sans, Mono, Serif | 1.1.0 | SIL Open Font License 1.1 | `vendor/plex/*.woff2` (Latin-1 subsets: Sans 400, 400 italic, 500, 600; Mono 400, 500; Serif 400, 400 italic, 600) | https://github.com/IBM/plex |
| Newsreader | variable, master of 9 Sep 2026 | SIL Open Font License 1.1 | `vendor/newsreader/Newsreader-Variable.woff2`, `Newsreader-Italic-Variable.woff2` (opsz 6-72, wght 200-800), `OFL.txt` | https://github.com/productiontype/Newsreader |
| marked | 18.0.12 | MIT | `vendor/marked/marked.umd.js`, `LICENSE.md` (renders Genesis's answers; the Studio reduces the output to a plain whitelist of elements) | https://github.com/markedjs/marked |
| Lucide | 1.43.0 (lucide-static) | ISC (parts of Feather Icons, MIT) | `vendor/lucide/sprite.svg` (the icons the Studio uses, as `<symbol>` elements) | https://lucide.dev |

AutomationBench is vendored separately under
`monarch-benchmark/workflowbench/vendor/automation-bench` (gitignored) and keeps
its own licence and provenance note (`VENDORED-FROM.txt`).

# Research: Archify, impeccable and enablement-video tools

Researched 02/11/2026. FOUND = checked at the source URL; INFERRED = reasoned.

Read-only, as of 02/11/2026. FOUND means I read it at the URL. INFERRED means my own deduction. Archify files are from main @ a406594, base https://github.com/tt-a1i/archify/blob/main.

## 1. Archify (v3.2.0, 2026-10-18, Apache-2.0)

- FOUND: it is an agent skill, not a standalone app. The agent writes a typed JSON file, and a Node CLI validates it and renders one self-contained HTML file (README_EN.md, archify/SKILL.md).
- FOUND: inputs are a prompt, a repository (code-backed diagrams with `SRC n` links), or Mermaid. Mermaid is re-authored by the agent, not parsed. There is no YAML or DSL.
- FOUND: output is HTML. The viewer's `E` menu exports a PNG to the clipboard, long images and PDF print. SKILL.md also claims SVG/WebM but the README doesn't confirm them.
- FOUND: Claude Code is a supported agent id in llms.txt, which installs the skill to `~/.claude/skills/`. Windows is not in the README. The changelog says v3.2.0 fixed "Windows command paths" and v2.13.0 ran the ZIP smoke test on Windows.
- FOUND: Windows needs Chrome or Edge (Edge ships with Win10) and a non-elevated shell. `ARCHIFY_CHROME` sets the browser path (archify/references/delivery-contract.md).
- FOUND: it needs Node 18 or later (root package.json).
- FOUND, production-grade look (DESIGN.md): dark default plus light (`T`), Signal Flow and Blueprint presets, 7 semantic colours, JetBrains Mono, a semantic icon per node, optional brand marks, SRC capsules. Animated flow (`trace`/`classic`, Live/Still button) respects reduced-motion.
- FOUND: the finalize gate runs validate, deliver, check and a real-browser check (6px text floor, no horizontal overflow).

### Steps on Windows 10 for (a) architecture diagram and (b) sequence/flow diagram

(The `claude-code` agent id and the Windows install path are INFERRED.)

1. Open a normal (non-elevated) PowerShell. Check `node -v` is 18 or later and that Edge or Chrome is installed.
2. `npx -y skills@latest add https://archify.si --list --full-depth` (llms.txt says proceed only if exactly one skill, `archify`, is listed).
3. `npx -y skills@latest add https://archify.si --skill archify --agent claude-code --global --copy --yes`
4. `node <installed-path>\bin\archify.mjs doctor`, then restart Claude Code.
5. (a) Prompt: "Use archify, type architecture. 12 components in 4 zones: sources, ingestion/triage, intelligence, outputs, all inside an AWS VPC boundary." List the nodes and edges.
   - The skill reads `examples/production-deployment.architecture.json`, writes `.archify/architecture-<slug>-<ts>/candidate.json`, then runs `node bin/archify.mjs finalize architecture candidate.json out.html --quality showcase --json`.
   - FOUND: that example has 12 components and nests a `security-group` (6 nodes) inside an "AWS us-east-1" `region` (9 nodes). Use the same pattern, with the VPC as the outer boundary and the 4 zones as inner boundaries.
   - FOUND: boundary kinds are only `region` and `security-group`. There is no `vpc` kind, so label it "AWS VPC". Node types are 7 (frontend, backend, database, cloud, security, messagebus, external).
   - INFERRED: four sibling zones inside one VPC should work, but the docs don't state nesting rules. Budget for a repair round on edge crossings.
6. (b) Prompt "Use archify, type sequence" (or `workflow`, or `dataflow` for pipeline lineage). It follows `examples/cache-miss-request.sequence.json` (participants, `messages` with integer `y` of 160 or more, `segments`, `activations`) and runs the same `finalize sequence ...` command.
7. Open the HTML in a browser. `node bin/archify.mjs demo <dir>` makes a sample.

### Known limits (FOUND unless marked)

- Out of scope per README: Mermaid auto-parse, general auto-layout, hosted sharing, WYSIWYG editing. It does not inspect live infrastructure and is "Not for dashboards".
- The agent hand-places coordinates and the router cannot rearrange boxes. The docs advise keeping canvas under 1240px wide; sequence self-message loops are unsupported.
- The bundled brand-mark catalog (checked via a raw fetch of `archify/brand-marks/catalog.json`) has no AWS or S3 marks. INFERRED: you get generic semantic icons plus AWS text labels.
- Elevated shells are unsupported on Windows. The skill is long (SKILL.md is about 19 KB plus references), so INFERRED: expect several minutes and a fair few tokens per diagram.

## 2. impeccable (v4.8.0, CLI released 2026-10-26, Apache-2.0)

https://github.com/pbakaus/impeccable

- FOUND: it is a design skill for coding agents. It adds 24 `/impeccable <command>` slash commands (steer, review, finish) and an anti-"AI slop" detector.
- FOUND: install with `npx impeccable install` from the project root, reload Claude Code, then run `/impeccable init`. That writes `PRODUCT.md`.
- FOUND: the alternative is `/plugin marketplace add pbakaus/impeccable`.
- For a small multi-tab page, run `/impeccable critique the tab bar`, then `typeset`, `colorize` and `layout`, then `polish`. Verify with `npx impeccable detect <file-or-url>`. Narrow targets work better than whole pages.
- FOUND: package.json lists a Windows binary (`@impeccable/cli-windows-x64`) and requires Node 18.19 or later.

## 3. Motion and video

- FOUND: "Claude Motion" is the real name, not "Claude Motion Design". It was launched by Anthropic on 2026-10-08 as a beta. https://claude.com/resources/articles/dashboards-and-motion, https://support.claude.com/en/articles/17454997-get-started-with-claude-motion
- FOUND: it is available on Team and Enterprise only. Enterprise owners must switch it on in Organization settings > Artifacts.
- FOUND: you start it with `/motion` or Output > Motion. Claude writes code that animates text, charts, shapes and images, and you export MP4. There is no video-generation model, and the docs state no maximum length. A 30-second explainer is Anthropic's own example. Fit is highest if your plan allows it, with the least control over frames.
- FOUND: Remotion v4.0.540 was released 2026-11-02. The free licence covers teams of up to 3 and incorporated single-person companies. Otherwise the Company licence is $25 per month per developer, including agent users. https://www.remotion.dev/docs/license/faq.md
- FOUND: install the skills with `npx skills add remotion-dev/skills` (https://www.remotion.dev/docs/ai/skills). Fit: mature and controllable, but it is a React project with a bundler, so setup is heavier for one day.
- FOUND: HyperFrames (HeyGen) is v0.9.6, released 2026-11-02, Apache-2.0. It renders HTML/CSS/GSAP to deterministic MP4 and needs Node 22+ and FFmpeg. A Windows desktop app exists. https://github.com/heygen-com/hyperframes
- FOUND: install the Claude Code plugin with `claude plugin marketplace add heygen-com/hyperframes` and `claude plugin install hyperframes@hyperframes`, then invoke `/hyperframes:hyperframes`.
- INFERRED ranking for a 30-second explainer in one day: Claude Motion if on Team/Enterprise, otherwise HyperFrames, with Remotion third.

## Not checked / risk

- I did not run any of this, so the Windows flow is untested.
- I did not read the Archify `viewer-runtime.md` reference, or the last 20 KB of its CHANGELOG.
- The "not on Free/Pro/Max" claim for Motion comes from a third-party summary of Anthropic's pricing page. Confirm your plan before relying on it.

# How to build this project with Claude Code

Build **one phase per Claude Code session**, in order. Each phase delivers something that works and can be tested before moving on.

| Phase | Spec | Result |
|---|---|---|
| 0 | `phase-0-foundation.md` | Server skeleton running; login and user management |
| 1 | `phase-1-catalogs-inventory.md` | Products, packaging, machines; spreadsheets imported; stock |
| 2 | `phase-2-work-orders.md` | Digital work orders; overselling blocked; printing |
| 3 | `phase-3-assignments-operator.md` | Full process without paper (manual operator controls) |
| 4 | `phase-4-plc-api-simulator.md` | PLC API working with simulated machines |
| 5 | `phase-5-real-plc.md` | Real PLCs connected (needs PLC model first) |
| 6 | `phase-6-dashboard.md` | Production dashboard |

Every session reads `CLAUDE.md` automatically, which points to `CONTEXT.md`, `00-overview.md` and `01-data-model.md`. Those keep all phases consistent.

## Prompt for each session

Start a **new** Claude Code session in the repository and paste (change the phase number):

```
Implement phase 1 following docs/specs/phase-1-catalogs-inventory.md.
First read CLAUDE.md, docs/CONTEXT.md, docs/specs/00-overview.md and docs/specs/01-data-model.md.
Write a short plan before coding. Do not build anything from later phases.
Finish by checking the "Definition of done" list, running all tests, and updating docs/PROGRESS.md.
```

If a session runs long, ask Claude Code to stop at a working point, update `docs/PROGRESS.md`, and continue in a new session with:

```
Continue phase N. Read docs/PROGRESS.md to see what is done.
```

## After each phase

1. Try it yourself in the browser (each phase spec has acceptance scenarios).
2. Commit to git.
3. If something should change, edit the spec first, then ask Claude Code to apply it.
4. When an open question is answered, update `CONTEXT.md` and the table in `00-overview.md` §10, then ask Claude Code to search for `TODO(OPEN-n)` and apply the decision.

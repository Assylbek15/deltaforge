# deltaforge

A release pipeline that aggregates job definitions from multiple dependency repositories,
generates XML artifacts with full traceability, and tracks incremental deployments across
multiple environments (dev / test / prod).

---

## Architecture

```
jobs-alpha  (team repo)  ──┐
                            ├──▶  deltaforge  ──▶  ALL_FILES.jar
jobs-beta   (team repo)  ──┘                  ──▶  CHANGED_FILES.jar (+ manifest.json)
```

`deltaforge` is the **release repository**. It pins each dependency at a specific tag via
`deps.json`, runs their generators on every release, and produces versioned artifacts.
Teams own their job repos independently; deltaforge controls what goes into each release.

---

## Repository layout

```
deltaforge/
├── deps.json                          # pins dependency repos by tag
├── environments/
│   ├── dev.json                       # current deployment state of dev
│   ├── test.json                      # current deployment state of test
│   └── prod.json                      # current deployment state of prod
├── tools/
│   ├── fetch_deps.py                  # clones deps at pinned tags, runs generators
│   ├── diff_generated_files.py        # diffs current vs previous, writes manifest
│   ├── create_archives.py             # builds ALL_FILES.jar and CHANGED_FILES.jar
│   ├── compute_deploy_diff.py         # chains CHANGED_FILES.jars into a net deploy set
│   └── resolve_deploy_chain.py        # resolves ordered release chain for deployment
└── .github/workflows/
    ├── release-generated-files.yml    # triggered on release publish
    └── deploy.yml                     # triggered manually to deploy to an environment
```

---

## Dependency repos

| Repo | Description |
|------|-------------|
| [jobs-alpha](https://github.com/Assylbek15/jobs-alpha) | Data team — user sync, data export, report builder |
| [jobs-beta](https://github.com/Assylbek15/jobs-beta) | Ops team — inventory check, notification sender |

Each repo exposes a `generate.py` entry point:

```bash
python generate.py --output-dir <dir> --version <tag>
```

Reads `SOURCE_COMMIT` and `RELEASE_VERSION` from the environment for traceability metadata.

---

## Release workflow

**Trigger:** publishing a GitHub release (or `workflow_dispatch` with an existing tag).

**Steps:**

1. Checkout at the release tag (reproducible — re-runs use the same code)
2. Clone each dependency at its pinned tag from `deps.json`
3. Run each dep's `generate.py` → `artifacts/current/<dep-name>/*.xml`
4. Diff current vs previous release → `artifacts/changed/`
5. Write `manifest.json` into `artifacts/changed/` (records added / modified / deleted)
6. Build `ALL_FILES.jar` (full snapshot) and `CHANGED_FILES.jar` (delta + manifest)
7. Upload both as release assets

### Pinning a dependency version

Edit `deps.json`:

```json
{
  "dependencies": [
    { "name": "jobs-alpha", "repo": "Assylbek15/jobs-alpha", "tag": "v1.1.1" },
    { "name": "jobs-beta",  "repo": "Assylbek15/jobs-beta",  "tag": "v1.1.1" }
  ]
}
```

Commit, push, publish a new deltaforge release. The workflow picks up the new tag automatically.

---

## Traceability

Every generated XML file contains a `<meta>` block:

```xml
<job name="user_sync">
  <meta>
    <source_tag>v1.1.1</source_tag>
    <source_commit>04bf5577cfb5e91012814701ba0155f48752337a</source_commit>
    <release_version>v1.1.0</release_version>
    <generated_at>2026-04-17T10:30:00Z</generated_at>
  </meta>
  ...
</job>
```

| Field | Meaning |
|-------|---------|
| `source_tag` | Tag of the dependency repo that produced this file |
| `source_commit` | Full git SHA of that dep repo commit |
| `release_version` | deltaforge release that triggered the generation |
| `generated_at` | UTC timestamp of generation |

Given any deployed file, you can trace back to the exact source commit with no external tooling.

---

## Incremental deployment

`CHANGED_FILES.jar` always contains `manifest.json` listing every change category:

```json
{
  "release": "v1.1.0",
  "previous_release": "v1.0.0",
  "generated_at": "2026-04-17T10:30:00Z",
  "changes": {
    "added":    ["jobs-alpha/report_builder.xml"],
    "modified": ["jobs-alpha/data_export.xml"],
    "deleted":  []
  }
}
```

To compute the net delta for an environment that is multiple releases behind, chain
the incremental JARs — **never download `ALL_FILES.jar`**:

```bash
python tools/compute_deploy_diff.py \
  --jars v1.1.0/CHANGED_FILES.jar v1.2.0/CHANGED_FILES.jar v1.3.0/CHANGED_FILES.jar \
  --output-dir deploy/to_apply \
  --output-manifest deploy/net_manifest.json
```

Merge rules applied oldest-to-newest:

| Sequence | Net result |
|----------|-----------|
| ADDED then MODIFIED | APPLY latest version |
| MODIFIED then MODIFIED | APPLY latest version |
| ADDED then DELETED | nothing (net zero) |
| DELETED then ADDED | APPLY (re-add wins) |

---

## Deploy workflow

**Trigger:** `Actions → Deploy to Environment → Run workflow`

**Inputs:**

| Input | Options | Description |
|-------|---------|-------------|
| `release_tag` | e.g. `v1.1.0` | Release to deploy |
| `environment` | `dev` / `test` / `prod` | Target environment |
| `deployment_type` | `standard` / `hotfix` | Controls promotion order enforcement |

### Standard deployment

Enforces `dev → test → prod` promotion order. Deploying to `prod` fails if `test`
is not already at the target release. Deploying to `test` fails if `dev` is not at
the target release.

```
publish v1.1.0
    → deploy to dev   (standard)  ✓
    → deploy to test  (standard)  ✓  (dev is at v1.1.0)
    → deploy to prod  (standard)  ✓  (test is at v1.1.0)
```

### Hotfix deployment

Skips the promotion order check. Use when a critical fix must reach prod immediately
without waiting for the full dev → test cycle.

```
publish v1.1.1 (hotfix)
    → deploy to prod  (hotfix)  ✓  (order check bypassed)
```

The `environments/prod.json` records `"deployment_type": "hotfix"` for the audit trail.

---

## Environment state

After each deployment the workflow commits an updated environment file:

```json
{
  "release":          "v1.1.0",
  "deployed_at":      "2026-04-17T10:30:00Z",
  "deployed_by":      "Assylbek15",
  "previous_release": "v1.0.0",
  "deployment_type":  "standard",
  "workflow_run_id":  "12345678"
}
```

**Useful queries:**

```bash
# What is on prod right now?
cat environments/prod.json

# Full deployment history for prod
git log --oneline environments/prod.json

# Compare dev and prod
diff environments/dev.json environments/prod.json

# Disaster recovery: which release to restore?
jq .release environments/prod.json
# → download ALL_FILES.jar from that release tag
```

---

## Local development

```bash
# Run the full pipeline locally (uses local_path from deps.json)
VERSION=v1.1.0 PREVIOUS_VERSION=v1.0.0 python tools/fetch_deps.py
VERSION=v1.1.0 PREVIOUS_VERSION=v1.0.0 python tools/diff_generated_files.py
python tools/create_archives.py

# Test chain-merge for a multi-release deploy
python tools/compute_deploy_diff.py \
  --jars dist/CHANGED_FILES.jar \
  --output-dir /tmp/deploy \
  --output-manifest /tmp/deploy/manifest.json
```

`deps.json` entries with a `local_path` field use the local directory when it exists,
falling back to GitHub clone automatically in CI.

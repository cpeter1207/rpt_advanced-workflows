# Local production-workspace containers

Run an explicit production workspace with the reusable launcher:

```sh
tools/run-in-quality-container.sh \
  ghcr.io/cpeter1207/rpt-advanced-quality-debian13:latest \
  /path/to/rpt_advanced make rust-coverage
```

The launcher pulls and reports the image digest, scopes cleanup to stopped
containers for that workspace, and removes its own labeled container on exit.

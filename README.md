# rpt_advanced-workflows

Workflow implementation repository for
[rpt_advanced](https://github.com/cpeter1207/rpt_advanced).

The project's [platform and quality requirements](https://github.com/cpeter1207/rpt_advanced/blob/main/QUALITY.md)
are maintained in the production repository. Workflow implementations belong
here; production code does not.

This repository currently contains setup documentation only. No workflows or
automated validation have been implemented. Production callers will follow
`main`; workflow-only updates must not themselves trigger production builds.

Branch protection requires pull requests, linear history, and resolved review
conversations, and prohibits force pushes and branch deletion. No nonexistent
status checks are required. Workflow validation must remain independent of
production tests so broken workflows can be repaired.

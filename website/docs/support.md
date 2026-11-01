---
title: Support and versioning policy
description: What support Netdryrun offers, how versions are numbered, what counts as a breaking change for the CLI, netdryrun.yml, the GitHub Action, the JSON report and the MCP tools, and how deprecations are announced.
---

# Support and versioning policy

## Support

Netdryrun is free open-source software under Apache-2.0, provided as is. Support for free use is best effort through [GitHub issues](https://github.com/netdryrun/Netdryrun/issues). Security reports get priority (see [Contact](contact.md)). There is no uptime or response-time guarantee for free use.

Only the latest release gets fixes. Upgrading is the fix for bugs in older releases.

## Version numbers

Netdryrun uses [semantic versioning](https://semver.org). Before 1.0, a minor release (0.2 to 0.3) may contain breaking changes; patch releases (0.2.0 to 0.2.1) never do. Every change is in the [changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md).

## What counts as a breaking change

These are the interfaces other tools and agents rely on:

| Interface | Stable contract |
|---|---|
| CLI | command names, flags, and exit codes (`0` passed, `1` failed, `2` error, `3` inconclusive) |
| `netdryrun.yml` | check types and keys; a file that validated keeps validating |
| JSON report | the `schema` field (`netdryrun.report/v1`); fields are only added within a schema version, never removed or renamed |
| GitHub Action | input and output names and their meaning; pin a tag or a commit SHA |
| MCP server | tool names, their arguments, and the `status` and `verdict` fields |

Removing or renaming any of these, or changing their meaning, is a breaking change. Adding is not: a new check type, a new report field, or a new `status` value (`inconclusive` was added after 0.2.0). Treat any status you don't know as not passed.

## Deprecation

Before something is removed, it keeps working for at least one minor release with a warning that names the replacement, and the changelog says so. After 1.0, removals wait for the next major version.

# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Continuous integration (GitHub Actions): `ruff` + `pytest` on Python 3.11 and 3.12, with a status badge.

## [0.1.0] - 2026-06-19

### Added
- Config-driven model registry (Anthropic + open models) with capability tags and coarse cost/speed tiers.
- Heuristic task-signal inference plus explicit override flags.
- Transparent weighted scoring with ranked alternatives and a human-readable rationale.
- `route` CLI: recommendation table, `--auto` (pipe-friendly id), `models`, and signal flags.
- Claude Code skill wrapper.

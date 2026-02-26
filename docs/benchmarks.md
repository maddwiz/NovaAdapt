# Benchmarks

This document defines the repeatable process for publishing NovaAdapt reliability numbers and head-to-head comparisons.

## 1) Run NovaAdapt Suite

```bash
PYTHONPATH=core:shared python3 -m novaadapt_core.cli benchmark \
  --config config/models.local.json \
  --suite config/benchmark.example.json \
  --out results/benchmark.novaadapt.json
```

## 2) Collect Baselines

Export other-system results in the same shape (`summary.total/passed/failed/success_rate/...`).

Example files:

- `results/benchmark.openclaw.json`
- `results/benchmark.claude-computer-use.json`
- `results/benchmark.ui-tars.json`

## 3) Produce Ranked Comparison

```bash
PYTHONPATH=core:shared python3 -m novaadapt_core.cli benchmark-compare \
  --primary results/benchmark.novaadapt.json \
  --primary-name NovaAdapt \
  --baseline OpenClaw=results/benchmark.openclaw.json \
  --baseline ClaudeComputerUse=results/benchmark.claude-computer-use.json \
  --baseline UITARS=results/benchmark.ui-tars.json \
  --out results/benchmark.compare.json \
  --out-md results/benchmark.compare.md \
  --md-title "NovaAdapt Reliability Benchmark"
```

The command outputs:

- ranked table by success rate
- first-try success rate
- action-count and blocked-count context
- delta vs NovaAdapt

## 4) Publish Table

`benchmark-compare --out-md` writes a publication-ready Markdown table with rank, success metrics, and delta vs primary.
Use generated outputs as source of truth for README/blog/social benchmark claims:

- `results/benchmark.compare.json`
- `results/benchmark.compare.md`

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from urllib import request


@dataclass
class HaloIntent:
    transcript: str
    confidence: float
    source: str = "halo"


def submit_intent(base_url: str, token: str | None, intent: HaloIntent) -> dict:
    body = {
        "objective": intent.transcript,
        "metadata": {
            "source": intent.source,
            "confidence": intent.confidence,
        },
    }
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(
        url=f"{base_url.rstrip('/')}/run_async",
        data=data,
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Halo wearable intent bridge prototype")
    parser.add_argument("--core-url", default="http://127.0.0.1:8787")
    parser.add_argument("--token", default=None)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--confidence", type=float, default=0.92)
    args = parser.parse_args()

    intent = HaloIntent(transcript=args.objective, confidence=max(0.0, min(1.0, args.confidence)))
    started = time.time()
    response = submit_intent(args.core_url, args.token, intent)
    elapsed_ms = int((time.time() - started) * 1000)
    print(json.dumps({"ok": True, "elapsed_ms": elapsed_ms, "response": response}, indent=2))


if __name__ == "__main__":
    main()

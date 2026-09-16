#!/usr/bin/env python3
"""Run the experimental external NWDAF-like analytics API."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from nwdaf_research.api.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--audit-path", type=Path, default=Path("logs/api_audit.jsonl"))
    parser.add_argument("--policy-config", type=Path, default=Path("configs/policy.yaml"))
    parser.add_argument("--model-artifact", type=Path, default=Path("models/rf-v1"))
    parser.add_argument("--response-agent-endpoint", default=os.environ.get("RESPONSE_AGENT_ENDPOINT"))
    parser.add_argument("--response-agent-api-key", default=os.environ.get("RESPONSE_AGENT_API_KEY"))
    args = parser.parse_args()
    uvicorn.run(
        create_app(
            args.raw_root,
            audit_path=args.audit_path,
            policy_config=args.policy_config,
            model_artifact=args.model_artifact,
            response_agent_endpoint=args.response_agent_endpoint,
            response_agent_api_key=args.response_agent_api_key,
        ),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
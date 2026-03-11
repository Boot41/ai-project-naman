from __future__ import annotations

import argparse
import asyncio
import json
from uuid import uuid4

from app.investigation_flow import run_investigation_pipeline


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Run OpsCopilot multi-agent workflow via Google ADK"
    )
    parser.add_argument("query", help="User query for investigation")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--request-id", default=None)
    parser.add_argument("--incident-key", default=None)
    parser.add_argument("--service-name", default=None)
    args = parser.parse_args()

    session_id = args.session_id or str(uuid4())
    request_id = args.request_id or f"req-{uuid4()}"

    result = await run_investigation_pipeline(
        request_id=request_id,
        session_id=session_id,
        user_id=args.user_id,
        query=args.query,
        incident_key=args.incident_key,
        service_name=args.service_name,
    )

    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(_main())

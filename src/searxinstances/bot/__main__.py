import asyncio
import os
import sys
import traceback

import cachetools
import httpx
import uvloop
import uvicorn
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from gidgethub import httpx as gh_httpx
from gidgethub import routing
from gidgethub import sansio


router = routing.Router()
cache = cachetools.LRUCache(maxsize=500)


@router.register("issue", action="opened")
async def issue_opened(event, gh, *arg, **kwargs):
    """Mark new PRs as needing a review."""
    issue = event.data["issue"]
    await gh.post(issue["comments_url"], data={body: "A new comment"})


@router.register("issue", action="renamed")
async def issue_opened(event, gh, *arg, **kwargs):
    pass


@router.register("issue", action="reopened")
async def issue_opened(event, gh, *arg, **kwargs):
    pass


async def main(request):
    try:
        body = await request.read()
        secret = os.environ.get("GH_SECRET")
        event = sansio.Event.from_http(request.headers, body, secret=secret)
        print('GH delivery ID', event.delivery_id, file=sys.stderr)

        if event.event == "ping":
            return PlainTextResponse(status=200)

        oauth_token = os.environ.get("GH_AUTH")
        async with httpx.AsyncClient(http2=True) as client:
            gh = gh_httpx.GitHubAPI(client, "dalf/botsandbox",
                                    oauth_token=oauth_token,
                                    cache=cache)
            # Give GitHub some time to reach internal consistency.
            await asyncio.sleep(1)
            await router.dispatch(event, gh)
        try:
            print('GH requests remaining:', gh.rate_limit.remaining)
        except AttributeError:
            pass
        return PlainTextResponse(status=200)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        return PlainTextResponse(status=500)


if __name__ == "__main__":
    # HOST / PORT
    # GH_SECRET / GH_AUTH
    app = Starlette(debug=True, routes=[Route("/", main), ])
    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", 8000)
    if port is not None:
        port = int(port)

    uvloop.install()
    uvicorn.run(app, host=host, port=port, log_level="info")

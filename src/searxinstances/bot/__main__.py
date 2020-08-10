import asyncio
import re
import os
import sys
import traceback
import rfc3986
import idna

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


TITLE_RE1 = re.compile('<([^>]+)>', re.IGNORECASE)
TITLE_RE2 = re.compile('((https://|http://)[^>]+)', re.IGNORECASE)


def host_use_http(host):
    tld = host.split('.')[-1]
    # onion and i2p can't part of an IP address
    return tld in ['onion', 'i2p']


def normalize_url(url):
    purl = rfc3986.urlparse(url)

    if purl.scheme is None and purl.host is None and purl.path is not None:
        # no protocol, no // : it is a path according to the rfc3986
        # but we know it is a host
        purl = rfc3986.urlparse('//' + url)

    if purl.scheme is None:
        # The url starts with //
        # Add https (or http for .onion or i2p TLD)
        if host_use_http(purl.host):
            purl = purl.copy_with(scheme='http')
        else:
            purl = purl.copy_with(scheme='https')

    # first normalization
    # * idna encoding to avoid misleading host
    # * remove query and fragment
    # * remove empty path
    purl = purl.copy_with(scheme=purl.scheme.lower(),
                          host=idna.encode(purl.host).decode('utf-8').lower(),
                          path='' if purl.path == '/' else purl.path,
                          query=None,
                          fragment=None)

    # only https (exception: http for .onion and .i2p TLD)
    if (purl.scheme == 'https' and not host_use_http(purl.host)) or\
       (purl.scheme == 'http' and host_use_http(purl.host)):
        # normalize the URL
        return rfc3986.normalize_uri(purl.geturl())

    #
    return None


def get_user_request_class(label_names: list):
    user_request_class = None
    for l_name in label_names:
        if l_name in LABEL_TO_CLASS:
            if user_request_class is None:
                user_request_class = LABEL_TO_CLASS[l_name]
            else:
                return None
    return user_request_class


def get_instance_url(title):
    title = title.replace('Add <searx instance url>', '')
    rtitle = re.search(TITLE_RE1, title)
    if rtitle is not None:
        return normalize_url(rtitle.group(1))
    rtitle = re.search(TITLE_RE2, title)
    if rtitle is not None:
        return normalize_url(rtitle.group(1))
    return None


async def parse_instance(issue, gh):
    title = issue['title']
    label_names = set(map(lambda label: label.get('name'), issue['labels']))
    print('label_names=', label_names)
    if 'instance add' in label_names:
        instance_url = get_instance_url(title)
        await gh.post(issue["comments_url"], data={"body": f"Instance {instance_url}"})


@router.register("issues", action="opened")
async def issue_opened(event, gh, *arg, **kwargs):
    await parse_instance(event.data["issue"], gh)


@router.register("issues", action="reopened")
async def issues_reopened(event, gh, *arg, **kwargs):
    await parse_instance(event.data["issue"], gh)


@router.register("issues", action="edited")
async def issues_reopened(event, gh, *arg, **kwargs):
    await parse_instance(event.data["issue"], gh)


@router.register("issues", action="labeled")
async def issues_reopened(event, gh, *arg, **kwargs):
    await parse_instance(event.data["issue"], gh)


@router.register("issue_comment", action="created")
async def issue_comment_created(event, gh, *arg, **kwargs):
    if event.data["comment"]["user"]["login"] == "searx-bot":
        return

    if event.data["comment"]["author_association"] not in ['COLLABORATOR', 'MEMBER', 'OWNER']:
        return

    print("issue", event.data["issue"]["body"])
    print("comment", event.data["comment"]["body"])


async def main(request):
    try:
        body = await request.body()
        secret = os.environ.get("GH_SECRET")
        event = sansio.Event.from_http(request.headers, body, secret=secret)
        print('GH delivery ID', event.delivery_id, file=sys.stderr)
        # print(event.event, event.data)
        if event.event == "ping":
            return PlainTextResponse(status_code=200)

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
        return PlainTextResponse(status_code=200)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        return PlainTextResponse(traceback.format_exc(), status_code=500)


if __name__ == "__main__":
    # HOST / PORT
    # GH_SECRET / GH_AUTH
    app = Starlette(debug=True, routes=[Route("/", main, methods=['GET', 'POST', 'PUT']), ])
    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", 8000)
    if port is not None:
        port = int(port)

    uvloop.install()
    uvicorn.run(app, host=host, port=port, log_level="info")

#!/usr/bin/env python

import argparse
import os
from functools import cache
import aiohttp
from aiohttp import web

parser = argparse.ArgumentParser(description="Web service to help with WeatherStation® 100WX")
parser.add_argument("-p", "--port", help="Port to run web server", action="store_true", default=9990)

args = parser.parse_args()


async def websocket_echo(request: web.Request) -> web.WebSocketResponse:
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    async for message in websocket:
        if message.type == aiohttp.WSMsgType.TEXT:
            await websocket.send_str(message.data)

    return websocket


async def data(request: web.Request) -> web.Response:
    return web.Response(status=200, body="test")


# pylint: disable=unused-argument
async def root(request: web.Request) -> web.Response:
    html_content = """
    <html>
        <head>
            <title>WeatherStation® 100WX</title>
        </head>
    </html>
    """
    return web.Response(text=html_content, content_type="text/html")

app = web.Application()
app.add_routes([web.get("/ws", websocket_echo)])
app.router.add_get("/", root, name="root")
app.router.add_get("/data", data, name="data")
web.run_app(app, path="0.0.0.0", port=args.port)

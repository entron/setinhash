# Update all feeds info.
# This script is supposed to run to fix problems or run before the initial run of ssb2hugo.
# Normally ssb2hugo.py will already keep the user info up to date after the initial run so no need to run this script regularly.

import logging
import asyncio
from asyncio import gather, create_task, run

from secret_handshake.network import SHSClient
from ssb.muxrpc import MuxRPCAPI, MuxRPCAPIException
from ssb.packet_stream import PacketStream, PSMessageType
from ssb.util import load_ssb_secret

import pathlib
import json
import utils
import os


# Define and create folders
print(utils.hugo_feeds_folder)
pathlib.Path(utils.hugo_feeds_folder).mkdir(parents=True, exist_ok=True)


async def update_feed_info(api, limit=-1):
    known_feeds = []
    async for msg in api.call('createFeedStream', [{
        'gt': 0,
        'limit': limit,
        'live': False,
        'keys': True,
        'values': True
    }], 'source'):
        data = json.loads(msg.data.decode('utf8'))
        # pprint(data)
        if type(data) is dict:
            content = data['value']['content']
            if type(content) is dict and 'type' in content:
                if content['type'] == 'about':
                    await utils.update_about(data, known_feeds)
    last = {'timestamp': 0, 'known_feeds': known_feeds}
    with open(os.path.join('last.json'), 'w') as f:
        json.dump(last, f)
    print(f'Number of known feeds {len(known_feeds)}.')


async def main():
    keypair = load_ssb_secret()['keypair']
    api = MuxRPCAPI()
    client = SHSClient('127.0.0.1', 8008, keypair, bytes(keypair.verify_key))
    packet_stream = PacketStream(client)
    await client.open()
    api.add_connection(packet_stream)

    task = create_task(update_feed_info(api, limit=-1))
    done, pending = await asyncio.wait([api, task], return_when=asyncio.FIRST_COMPLETED)


asyncio.run(main())

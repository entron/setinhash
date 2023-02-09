# Manually remove and block a feed (e.g. illegal content, bot etc.)

import asyncio
from asyncio import gather, create_task, run

from secret_handshake.network import SHSClient
from ssb.muxrpc import MuxRPCAPI, MuxRPCAPIException
from ssb.packet_stream import PacketStream, PSMessageType
from ssb.util import load_ssb_secret

import utils
import argparse


# Define and create folders
print(utils.hugo_feeds_folder)


async def remove_feed(api, id):
    utils.remove_feed(id)
    await utils.block(api, id)
    await utils.delete_feed_messages(api, id)


async def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("feed", help="feed id to remove")
    args = parser.parse_args()
    feed = args.feed

    keypair = load_ssb_secret()['keypair']
    api = MuxRPCAPI()
    client = SHSClient('127.0.0.1', 8008, keypair, bytes(keypair.verify_key))
    packet_stream = PacketStream(client)
    await client.open()
    api.add_connection(packet_stream)

    task = create_task(remove_feed(api, feed))
    done, pending = await asyncio.wait([api, task], return_when=asyncio.FIRST_COMPLETED)


asyncio.run(main())

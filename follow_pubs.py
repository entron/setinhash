# Follow newly founded pubs (must has a domain name).
# This script should be run from time to time (e.g. daily, weekly) to find new users.

import logging
import asyncio
from asyncio import gather, create_task, run

from secret_handshake.network import SHSClient
from ssb.muxrpc import MuxRPCAPI, MuxRPCAPIException
from ssb.packet_stream import PacketStream, PSMessageType
from ssb.util import load_ssb_secret

from pprint import pprint
import json
import utils
import os


async def follow_pubs(api):
    # Replace the feed_id with yours.
    followed_pubs = await utils.get_following(api, feed_id="@DdZpsI3GdLm+DlivDRVJCmRS5FyQIcjlL4m68WLLkg0=.ed25519")

    with open(os.path.join(utils.SSB_ROOT, 'gossip.json'), 'r') as f:
        gossip = json.load(f)

    pub_with_domain = []
    for pub in gossip:
        host = pub['host']
        key = pub['key']
        if sum(c.isalpha() for c in host) > 0:
            pub_with_domain.append(key)

    pub_to_follow = set(pub_with_domain) - set(followed_pubs)

    for pub in pub_to_follow:
        await utils.follow(api, pub)


async def main():
    keypair = load_ssb_secret()['keypair']
    api = MuxRPCAPI()
    client = SHSClient('127.0.0.1', 8008, keypair, bytes(keypair.verify_key))
    packet_stream = PacketStream(client)
    await client.open()
    api.add_connection(packet_stream)

    task = create_task(follow_pubs(api))
    done, pending = await asyncio.wait([api, task], return_when=asyncio.FIRST_COMPLETED)
    r = await task
    pprint(r)

asyncio.run(main())

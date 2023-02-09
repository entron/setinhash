# Fetching and upload blobs to bucket.

import logging
import time
import asyncio
from asyncio import gather, create_task, run

from secret_handshake.network import SHSClient
from ssb.muxrpc import MuxRPCAPI, MuxRPCAPIException
from ssb.packet_stream import PacketStream, PSMessageType
from ssb.util import load_ssb_secret

import sqlite3
import utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('setinhash.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


async def check_has(api, r):
    has = []
    miss = []
    for row in r:
        msg = await api.call('blobs.has', [row[0]], 'async')
        if msg.data.decode('utf8') == 'true':
            has.append(row)
        else:
            miss.append(row)
    return has, miss


async def want(api, miss_ids):
    results = []
    for mid in miss_ids:
        try:
            msg = await asyncio.wait_for(api.call('blobs.want', [mid], 'async'), timeout=10.0)
            results.append(msg.data.decode('utf8'))
            logger.info(f"Want: {mid}.")
        except asyncio.TimeoutError:
            results.append('timeout')
            logger.info(f"Timeout want: {mid}.")
    return results


async def check_and_want(api, r, conn_blobs):
    has, miss = await check_has(api, r)
    utils.upload(has)
    has_ids = [row[0] for row in has]
    miss_ids = [row[0] for row in miss]
    utils.mark_has(conn_blobs, has_ids)
    result = await want(api, miss_ids)
    utils.add_n_wanted(conn_blobs, miss_ids)
    return result


async def main():
    keypair = load_ssb_secret()['keypair']
    api = MuxRPCAPI()

    client = SHSClient('127.0.0.1', 8008, keypair, bytes(keypair.verify_key))
    packet_stream = PacketStream(client)

    await client.open()
    api.add_connection(packet_stream)

    conn_blobs = sqlite3.connect(utils.blobs_path)

    r = conn_blobs.execute(
        "SELECT * FROM blobs WHERE has = 0 AND n_wanted <= 1 ORDER BY n_wanted DESC LIMIT 100")

    task = create_task(check_and_want(api, r, conn_blobs))
    done, pending = await asyncio.wait([api, task], return_when=asyncio.FIRST_COMPLETED)

    conn_blobs.close()


asyncio.run(main())

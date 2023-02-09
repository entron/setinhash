import logging
import asyncio
from asyncio import gather, create_task, run

from colorlog import ColoredFormatter

from secret_handshake.network import SHSClient
from ssb.muxrpc import MuxRPCAPI, MuxRPCAPIException
from ssb.packet_stream import PacketStream, PSMessageType
from ssb.util import load_ssb_secret

from pprint import pprint
import json
import os
import pathlib
import sqlite3
import utils
import argparse


# Define and create folders
print(utils.hugo_feeds_folder)
pathlib.Path(utils.hugo_feeds_folder).mkdir(parents=True, exist_ok=True)
pathlib.Path(utils.hugo_threads_folder).mkdir(parents=True, exist_ok=True)


async def ssb2hugo(api, gt, known_feeds, threads, root_map, blocked_feeds, method='createFeedStream', limit=-1, initialize=False):
    blobs = []
    blobs_mention = []
    conn_blobs = sqlite3.connect(utils.blobs_path)
    conn_blobs_mention = sqlite3.connect(utils.blobs_mention_path)
    utils.ct_blobs(conn_blobs)
    utils.ct_blobs_mention(conn_blobs_mention)

    public_feeds, private_feeds = utils.load_public_private_feeds()

    async for msg in api.call(method, [{
        'gt': gt,
        'limit': limit,
        'live': False,
        'keys': True,
        'values': True
    }], 'source'):
        data = json.loads(msg.data.decode('utf8'))
        # pprint(data)
        if type(data) is dict:
            author = data['value']['author']
            if author in blocked_feeds:
                continue
            content = data['value']['content']
            if method == 'createFeedStream':
                last_ts = data['value']['timestamp']
            elif method == 'createLogStream':
                last_ts = data['timestamp']
            if type(content) is dict and 'type' in content:
                if content['type'] == 'about' and not initialize:
                    await utils.update_about(data, known_feeds, api, threads)
                elif content['type'] == 'post':
                    if author in public_feeds:
                        try:
                            utils.create_post(data, threads, root_map)
                        except:
                            continue
                     # For the moment most people did not set publicwebhosting and believe most of those will set true
                     # so to speed up blobs downloading I will download here but set the link as private.
                    if author not in private_feeds:
                        utils.extract_blobs(data, blobs, blobs_mention)
    with open('threads_with_ts.json', 'w') as f:
        json.dump(threads, f)
    with open('root_map.json', 'w') as f:
        json.dump(root_map, f)
    threads_for_hugo = {}
    for key, value in threads.items():
        value.sort(key=lambda x: x[1])
        threads_for_hugo[key] = [x[0] for x in value]
    with open(os.path.join(utils.hugo_threads_folder + 'threads.json'), 'w') as f:
        json.dump(threads_for_hugo, f)

    last = {'timestamp': last_ts, 'known_feeds': known_feeds}
    with open(os.path.join('last.json'), 'w') as f:
        json.dump(last, f)
    utils.print_timestamp(last_ts)
    print(f'Number of known feeds {len(known_feeds)}.')

    utils.insert_blob(conn_blobs, blobs)
    utils.insert_blob_mention(conn_blobs_mention, blobs_mention)
    conn_blobs.close()
    conn_blobs_mention.close()


async def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--initialize", help="run from scratch",
                        action="store_true")
    args = parser.parse_args()
    if args.initialize:
        print("Initial run ...")

    try:
        with open('last.json', 'r') as f:
            last = json.load(f)
    except:
        last = {'timestamp': 0, 'known_feeds': []}

    try:
        with open('threads_with_ts.json', 'r') as f:
            threads = json.load(f)
    except:
        threads = {}

    try:
        with open('root_map.json', 'r') as f:
            root_map = json.load(f)
    except:
        root_map = {}

    with open('blocked_feeds.txt') as f:
        c = f.readlines()
    blocked_feeds = [x.strip() for x in c] 

    utils.print_timestamp(last['timestamp'])
    keypair = load_ssb_secret()['keypair']
    api = MuxRPCAPI()
    client = SHSClient('127.0.0.1', 8008, keypair, bytes(keypair.verify_key))
    packet_stream = PacketStream(client)
    await client.open()
    api.add_connection(packet_stream)

    task = create_task(ssb2hugo(api, method='createLogStream', gt=last['timestamp'],
                                known_feeds=last['known_feeds'], threads=threads,
                                root_map=root_map, blocked_feeds=blocked_feeds,
                                limit=-1, initialize=args.initialize))
    done, pending = await asyncio.wait([api, task], return_when=asyncio.FIRST_COMPLETED)


asyncio.run(main())

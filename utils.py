import base64
import json
import os
from os import listdir
from os.path import isfile, join
from datetime import datetime
import pathlib
import re
from pprint import pprint
import sqlite3
import shutil
import boto3
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('setinhash.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

name_regex = "[^]]+"
url_regex = "[^)]+"

markdown_link = f'\[({name_regex})]\(\s*({url_regex})\s*\)'
blob_link = r"([&][A-Za-z0-9\/+]{43}=\.[\w\d]+)"
post_link = r"([%][A-Za-z0-9\/+]{43}=\.[\w\d]+)"

h1 = re.compile(r'(?m)^#(?!#)(.*)')

# Replace with yours
BLOB_DOMAIN = 'https://blob.setinhash.com/'
SSB_ROOT = '/root/ssb-pub-data/'
HUGO_ROOT = '/root/hugo/'

hugo_feeds_folder = os.path.join(HUGO_ROOT, 'data/feeds/')
hugo_threads_folder = os.path.join(HUGO_ROOT, 'data/threads/')
hugo_content_folder = os.path.join(HUGO_ROOT, 'content/')

blobs_path = 'blobs.sqlite'
blobs_mention_path = 'blobs_mention.sqlite'

# Replace with yours
s3config = {
    "region_name": '',
    "endpoint_url": '',
    "aws_access_key_id": '',
    "aws_secret_access_key": ''}

resource = boto3.resource("s3", **s3config)
blob_bucket = resource.Bucket('blob-sh')


def print_timestamp(ts):
    ts = int(ts)
    ts /= 1000
    print(datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'))


def ssbid2hex(id):
    return base64.b64decode(id.split('.')[0][1:]).hex()


def load_feed(hex):
    with open(os.path.join(hugo_feeds_folder, hex + '.json'), 'r') as f:
        return json.load(f)


def load_public_private_feeds():
    public_feeds = []
    private_feeds = []
    paths = [join(hugo_feeds_folder, f) for f in listdir(hugo_feeds_folder)]
    print(f"Number of feeds: {len(paths)}")
    for path in paths:
        with open(path, 'r') as f:
            feed = json.load(f)
            if 'publicWebHosting' in feed and feed['publicWebHosting'] is True:
                public_feeds.append(feed['id'])
            if 'publicWebHosting' in feed and feed['publicWebHosting'] is False:
                private_feeds.append(feed['id'])
    return public_feeds, private_feeds


async def add_public_feed_post_history(api, public_feed_id, threads):
    blobs = []
    blobs_mention = []
    conn_blobs = sqlite3.connect(blobs_path)
    conn_blobs_mention = sqlite3.connect(blobs_mention_path)

    async for msg in api.call('createHistoryStream', [{
        'id': public_feed_id,
        'gt': 0,
        'limit': -1,
        'live': False,
        'keys': True,
        'values': True
    }], 'source'):
        data = json.loads(msg.data.decode('utf8'))
        # pprint(data)
        if type(data) is dict:
            content = data['value']['content']
            if type(content) is dict and 'type' in content:
                # if content['type'] == 'about':  # Do not call this casue this will cause a loop
                if content['type'] == 'post':
                    try:
                        create_post(data, threads)
                    except:
                        continue
                    extract_blobs(data, blobs, blobs_mention)

    insert_blob(conn_blobs, blobs)
    insert_blob_mention(conn_blobs_mention, blobs_mention)
    conn_blobs.close()
    conn_blobs_mention.close()


def remove_feed(id, remove_blobs=True):
    hex = ssbid2hex(id)
    # try:
    #     os.remove(os.path.join(hugo_feeds_folder, hex + '.json'))
    #     logger.info(f"Removed feed {hex}")
    # except:
    #     logger.info(f"Feed {hex} was not stored thus not removed.")

    post_folder = os.path.join(hugo_content_folder, f'posts/{hex}/')
    reply_folder = os.path.join(hugo_content_folder, f'replies/{hex}/')
    try:
        shutil.rmtree(post_folder)
        logger.info(f"Removed {post_folder}")
    except:
        logger.info(f"{post_folder} was not stored thus not removed.")

    try:
        shutil.rmtree(reply_folder)
        logger.info(f"Removed {reply_folder}")
    except:
        logger.info(f"{reply_folder} was not stored thus not removed.")

    if remove_blobs:
        delete_blobs_of_feed(id)


def load_threads():
    with open(os.path.join(hugo_threads_folder, 'threads.json'), 'r') as f:
        return json.load(f)


def create_hugo_build_option(folder, option, cascade_option):
    frontmatter = {}
    frontmatter['_build'] = option
    frontmatter['cascade'] = {'_build': cascade_option}
    with open(os.path.join(folder, '_index.html'), 'w') as f:
        f.write(json.dumps(frontmatter))


async def update_about(data, known_feeds, api=None, threads=None):
    feed_hex = ssbid2hex(data['value']['author'])
    content = data['value']['content']

    if 'about' not in content or content['about'] != data['value']['author']:
        return

    if feed_hex in known_feeds:
        feed = load_feed(feed_hex)
        known = True
    else:
        feed = {}
        feed['id'] = data['value']['author']
        feed['hex'] = feed_hex
        known = False

    if 'name' in content:
        feed['name'] = content['name']

    if 'image' in content and type(content['image']) is str:
        feed['image'] = content['image']
    elif 'image' in content and type(content['image']) is dict and 'link' in content['image']:
        feed['image'] = content['image']['link']

    if 'description' in content:
        feed['description'] = content['description']

    if 'publicWebHosting' in content:
        if api and threads and known:  # Only retrieve history when known because otherwise the history will arrive latter anyway.
            if ('publicWebHosting' not in feed or feed['publicWebHosting'] is False) and content['publicWebHosting']:
                await add_public_feed_post_history(api, feed['id'], threads)
                reset_blobs_acl_of_feed(feed['id'], 'public-read')
                logger.info(f"{feed['id']} set publicWebHosting = True. Added histrical posts.")
            elif ('publicWebHosting' in feed and feed['publicWebHosting'] is True) and content['publicWebHosting'] is False:
                remove_feed(feed['id'])
                logger.info(f"{feed['id']} set publicWebHosting = False. Removed histrical posts.")
        feed['publicWebHosting'] = True if str(content['publicWebHosting']).lower() == 'true' else False

    with open(os.path.join(hugo_feeds_folder, feed_hex + '.json'), 'w') as f:
        json.dump(feed, f)
    if not known:
        known_feeds.append(feed_hex)


def replace_markdown_link(text):
    for match in re.findall(markdown_link, text):
        link = match[1]
        if link[0] == '&':
            try:
                hex = ssbid2hex(link)
            except:
                continue
            new_link = BLOB_DOMAIN + hex[:2] + '/' + hex[2:]
            text = text.replace(link, new_link)
        elif link[0] == '%':
            try:
                hex = ssbid2hex(link)
            except:
                continue
            new_link = '/posts/' + hex
            text = text.replace(link, new_link)
        elif link[0] == '@':
            try:
                hex = ssbid2hex(link)
            except:
                continue
            new_link = '/feeds/' + hex
            text = text.replace(link, new_link)
    return text


def replace_naked_post_link(text):  #post link not inside markdown format []() 
    for link in re.findall(post_link, text):
        try:
            hex = ssbid2hex(link)
        except:
            continue
        new_link = '/posts/' + hex
        markdown_format = f"[{link[:4]}]({new_link})"
        text = text.replace(link, markdown_format)
    return text


def link_channel(text):
    hashtags = [token for token in text.split() if len(
        token) >= 2 and token[0] == '#' and token[1] != '#']
    hashtags = list(set(hashtags))
    for tag in hashtags:
        linked_channels = f"[{tag}](/channels/{tag[1:]})"
        text = text.replace(tag, linked_channels)
    return text


def extract_channels(content):
    if 'channel' in content and content['channel']:
        channel = content['channel']
        if not any([x in channel for x in ['#', '%', '/', '\\', '@', '&']]):
            channels = [channel]
    else:
        channels = []
    return channels


def extract_title(text):
    text = text.strip()
    if text[:2] == '# ' or text[:3] == '## ' or text[:4] == '### ':
        title = text.partition('\n')[0].replace('#', '').strip()
    else:
        h1 = re.compile(r'(?m)^#(?!#)(.*)')
        m = h1.search(text)
        if m:
            title = m.group(1).strip()
        else:
            title = ""
    return title


def extract_blobs(data, blobs, blobs_mention):
    content = data['value']['content']
    if 'mentions' in content:
        author = data['value']['author']
        ts = data['value']['timestamp']
        if type(content['mentions']) is list:
            for m in content['mentions']:
                if type(m) is dict and 'link' in m and type(m['link']) is str:
                    r = re.match(blob_link, m['link'])
                    if r:
                        link = r[0]
                        blobs_mention.append((str(link), str(author), str(data['key']), int(ts)))
                        if 'name' in m:
                            name = m['name']
                        else:
                            name = ''
                        try:
                            size = m['size']
                            blob_type = m['type']
                            blobs.append((str(link), str(name), int(size), str(blob_type), 0, 0))
                        except:
                            continue


def get_root(root_map, post_id):
    if post_id not in root_map:
        return post_link
    if root_map[post_id] in root_map:
        return get_root(root_map, root_map[post_id])
    else:
        return root_map[post_id]


def create_post(data, threads, root_map):
    content = data['value']['content']
    post_hex = ssbid2hex(data['key'])
    feed_hex = ssbid2hex(data['value']['author'])
    # filename = base64.urlsafe_b64encode(data['key'].encode("utf-8")).decode('utf-8') + '.md'
    # url = quote_plus(data['key'])
    ts = data['value']['timestamp']
    ts /= 1000
    dt_str = datetime.utcfromtimestamp(ts).isoformat(timespec='seconds')
    text = str(data['value']['content']['text'])
    if len(text) < 140:
        return
    text = replace_markdown_link(text)
    text = replace_naked_post_link(text)
    text = link_channel(text)
    channels = extract_channels(content)

    frontmatter = {}
    frontmatter["title"] = extract_title(text)
    frontmatter["id"] = data['key']
    frontmatter["date"] = dt_str
    frontmatter["feeds"] = [feed_hex]
    frontmatter["channels"] = channels
    if text.count('$') > 1:
        frontmatter["math"] = True
    if 'root' in content and len(content['root']) > 50:
        root_map[data['key']] = content['root']
        frontmatter["threads"] = ssbid2hex(get_root(root_map, data['key']))
        frontmatter["type"] = "reply"
        folder = f'replies/{feed_hex}/'
    else:
        frontmatter["threads"] = post_hex
        frontmatter["type"] = "root"
        folder = f'posts/{feed_hex}/'
    folder_full_path = os.path.join(hugo_content_folder, folder)
    pathlib.Path(folder_full_path).mkdir(parents=True, exist_ok=True)
    path = folder + post_hex + '.md'
    if frontmatter["threads"] in threads:
        threads[frontmatter["threads"]].append((path, data['value']['timestamp']))
    else:
        threads[frontmatter["threads"]] = [(path, data['value']['timestamp'])]

    # frontmatter["aliases"] = ['/posts/' + quote_plus(data['key'])] # seems % is not accepted by hugo in link

    with open(os.path.join(hugo_content_folder, path), 'w') as f:
        f.write(json.dumps(frontmatter))
        f.write('\n\n')
        f.write(text)


async def createHistoryStream(api, feed_id):
    async for msg in api.call('createHistoryStream', [{
        'id': feed_id,
        'live': False,
    }], 'source'):
        pprint(json.loads(msg.data.decode('utf8')))


async def publish(api, content):
    msg = await api.call('publish', [content], 'async')
    print(msg)


async def follow(api, feed_link):
    await publish(api, {'type': 'contact', 'contact': feed_link, 'following': True})


async def unfollow(api, feed_link):
    await publish(api, {'type': 'contact', 'contact': feed_link, 'following': False})


async def block(api, feed_link):
    await publish(api, {'type': 'contact', 'contact': feed_link, 'following': False, 'blocking': True})


async def backlinks(api):
    async for msg in api.call('backlinks.read', [{
        'query': [{'$filter': {'dest': "#ssb-faq"}}],
        'index': 'DTA',
        'live': False,
    }], 'source'):
        pprint(json.loads(msg.data.decode('utf8')))


async def get(api, message_id):
    msg = await api.call('get', [message_id], 'async')
    pprint(json.loads(msg.data.decode('utf8')))


async def delete_feed_messages(api, feed_id):
    msg = await api.call('del', [feed_id], 'async')
    pprint(json.loads(msg.data.decode('utf8')))


async def query(api):
    async for msg in api.call('query.read', [{
        'query': [
            {"$filter": {"value": {"content": {"channel": {"$is": "string"}, "type": "post"}}}},
            {"$reduce": {
                "channel": ["value", "content", "channel"],
                "count": {"$count": True},
                "timestamp": {"$max": ["value", "timestamp"]}
            }},
            {"$sort": [["timestamp"], ["count"]]}
        ],
        'live': False,
    }], 'source'):
        pprint(json.loads(msg.data.decode('utf8')))


async def links(api, source=None, dest=None, rel=None):
    results = []
    async for msg in api.call('links', [{
        'source': source,
        'dest': dest,
        'rel': rel,
        'live': False,
        'keys': True,
        'values': True
    }], 'source'):
        results.append((json.loads(msg.data.decode('utf8'))))
    return results


async def get_following(api, feed_id):
    r = await links(api, source=feed_id, dest="@", rel='contact')
    following = []
    for m in r:
        if type(m) is dict:
            content = m['value']['content']
            try:
                if content['following'] == True:
                    following.append(content['contact'])
            except:
                pass
    return following


async def messagesByType(api, m_type, r):
    async for msg in api.call('messagesByType', [{
        'type': m_type,
        'live': False,
    }], 'source'):
        # pprint(json.loads(msg.data.decode('utf8')))
        r.append(json.loads(msg.data.decode('utf8')))


async def top_posts(api):
    async for msg in api.call('query.read', [{
        'query': [
            {"$filter": {"value": {"content": {"channel": {"$is": "string"}, "type": "post"}}}},
            {"$reduce": {
                "channel": ["value", "content", "channel"],
                "count": {"$count": True},
                "timestamp": {"$max": ["value", "timestamp"]}
            }},
            {"$sort": [["timestamp"], ["count"]]}
        ],
        'live': False,
    }], 'source'):
        pprint(json.loads(msg.data.decode('utf8')))


def ct_blobs(conn):
    with conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS blobs
               (blob_id TEXT NOT NULL PRIMARY KEY,
                name TEXT,
                size INTEGER,
                type TEXT,
                has INTEGER,
                n_wanted INTEGER)''')


def ct_blobs_mention(conn):
    with conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS blobs_mention
               (blob_id TEXT NOT NULL,
                by_user_id TEXT,
                by_post_id TEXT,
                timestamp BIGINT,
                PRIMARY KEY (blob_id, by_post_id)
                )''')


def insert_blob(conn, data):
    with conn:
        conn.executemany(
            'INSERT OR IGNORE INTO blobs VALUES (?,?,?,?,?,?)', data)


def insert_blob_mention(conn, data):
    with conn:
        conn.executemany(
            'INSERT OR IGNORE INTO blobs_mention VALUES (?,?,?,?)', data)


async def blobs_want(api, blob_id):
    msg = await api.call('blobs.want', [blob_id], 'async')
    pprint(msg)


async def blobs_has(api, blob_id):
    msg = await api.call('blobs.has', [blob_id], 'async')
    pprint(msg)


def mark_has(conn, has_ids):
    sql = "UPDATE blobs SET has = 1 WHERE blob_id in ({seq})".format(
        seq=','.join(['?']*len(has_ids)))
    with conn:
        conn.execute(sql, has_ids)


def add_n_wanted(conn, miss_ids):
    sql = "UPDATE blobs SET n_wanted = n_wanted + 1 WHERE blob_id in ({seq})".format(
        seq=','.join(['?']*len(miss_ids)))
    with conn:
        conn.execute(sql, miss_ids)


def get_blob_filename(blob_id):
    hex = ssbid2hex(blob_id)
    folder = hex[:2]
    filename = hex[2:]
    return folder, filename


def get_author(blob_id, conn):
    with conn:
        r = next(conn.execute('SELECT * FROM blobs_mention WHERE blob_id = ? ORDER BY timestamp LIMIT 1', (blob_id,)))
        return r[1]


def upload(has):
    public_feeds, private_feeds = load_public_private_feeds()
    conn_blobs_mention = sqlite3.connect(blobs_mention_path)

    blob_root = os.path.join(SSB_ROOT, 'blobs/sha256/')

    for row in has:
        id = row[0]
        content_type = row[3]
        feed_id = get_author(id, conn_blobs_mention)
        if feed_id in private_feeds:
            continue
        folder, filename = get_blob_filename(id)
        local_path = os.path.join(blob_root, folder, filename)
        if not os.path.isfile(local_path):
            logging.warning(f"File does not exist: {local_path}")
        remote_path = os.path.join(folder, filename)
        args = {"CacheControl": "public,max-age=604800,immutable", "ContentType": content_type}
        if feed_id in public_feeds:
            args["ACL"] = "public-read"
        else:
            args["ACL"] = "private"

        blob_bucket.upload_file(local_path,
                                remote_path,
                                ExtraArgs=args
                                )
        logger.info(f"Upload {id} to {remote_path}")

    conn_blobs_mention.close()


def delete_blobs_of_feed(feed_id):
    conn_blobs_mention = sqlite3.connect(blobs_mention_path)
    conn_blobs = sqlite3.connect(blobs_path)

    for row in conn_blobs_mention.execute('SELECT * FROM blobs_mention WHERE by_user_id = ?', (feed_id,)):
        blob_id = row[0]
        author = get_author(blob_id, conn_blobs_mention)
        if author == feed_id:
            folder, filename = get_blob_filename(blob_id)
            remote_path = os.path.join(folder, filename)
            resource.Object('blob-sh', remote_path).delete()
            conn_blobs.execute('DELETE FROM blobs WHERE blob_id = ?', (blob_id,))
            logger.info(f"Deleted {remote_path}.")

    conn_blobs.commit()
    conn_blobs.close()
    conn_blobs_mention.execute('DELETE FROM blobs_mention WHERE by_user_id = ?', (feed_id,))
    conn_blobs_mention.commit()
    conn_blobs_mention.close()


def reset_blobs_acl_of_feed(feed_id, acl):
    conn_blobs_mention = sqlite3.connect(blobs_mention_path)
    for row in conn_blobs_mention.execute('SELECT * FROM blobs_mention WHERE by_user_id = ?', (feed_id,)):
        blob_id = row[0]
        author = get_author(blob_id, conn_blobs_mention)
        if author == feed_id:
            folder, filename = get_blob_filename(blob_id)
            remote_path = os.path.join(folder, filename)
            obj = blob_bucket.Object(remote_path)
            try:
                obj.Acl().put(ACL=acl)
                logger.info(f"Set {remote_path} as {acl}")
            except Exception as err:
                logger.info(err)
                logger.info(f'Reseting ACL {blob_id} of {feed_id} failed. (probably due to it has not been uploaded yet.)')
    conn_blobs_mention.close()
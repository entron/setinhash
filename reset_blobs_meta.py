# Reset all blobs ACL in the bucket according to the feed info. 
# Should run update_feed_info.py first to make sure the ACL is up to date.
# This script is supposed to run to fix problems in ACL.

import logging
import os
import sqlite3
import utils
import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('setinhash.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

conn_blobs = sqlite3.connect(utils.blobs_path)
conn_blobs_mention = sqlite3.connect(utils.blobs_mention_path)

public_feeds, private_feeds = utils.load_public_private_feeds()

# Filling in with your information
s3config = {
    "region_name": '',
    "endpoint_url": '',
    "aws_access_key_id": '',
    "aws_secret_access_key": ''}

resource = boto3.resource("s3", **s3config)
blob_bucket = resource.Bucket('blob-sh')

with conn_blobs:
    for row in conn_blobs.execute('SELECT * FROM blobs WHERE has = 1'):
        blob_id = row[0]
        content_type = row[3]
        folder, filename = utils.get_blob_filename(blob_id)
        remote_path = os.path.join(folder, filename)
        feed_id = utils.get_author(blob_id, conn_blobs_mention)

        if feed_id in public_feeds:
            acl = "public-read"
        else:
            acl = "private"

        obj = blob_bucket.Object(remote_path)
        # obj.Acl().put(ACL=acl) merged into copy_from
        obj.copy_from(
            CopySource={
                'Bucket': 'blob-sh',
                'Key': obj.key,
            },
            ACL=acl,
            CacheControl='public,max-age=604800,immutable',
            ContentType=content_type,
            MetadataDirective='REPLACE',
        )

        logger.info(f"Set {remote_path} as {acl} and content-type as {content_type}")

conn_blobs.close()
conn_blobs_mention.close()

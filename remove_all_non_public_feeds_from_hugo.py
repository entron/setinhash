# Remove all non public feeds content from hugo folder. This script is only used occasionally to clean.
import utils
import json
from os import listdir
from os.path import isfile, join


paths = [join(utils.hugo_feeds_folder, f) for f in listdir(utils.hugo_feeds_folder)]
for path in paths:
    with open(path, 'r') as f:
        feed = json.load(f)
        if 'publicWebHosting' not in feed:
            utils.remove_feed(feed['id'], remove_blobs=False)
        elif feed['publicWebHosting'] is False:
            utils.remove_feed(feed['id'], remove_blobs=True)
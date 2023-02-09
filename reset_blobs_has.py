# Reset blob has and blob wants in blobs.sqlite based on bucket.
import utils
import sqlite3
import os

all_keys = [obj.key for obj in utils.blob_bucket.objects.all()]
print(f"Number of keys: {len(all_keys)}")

conn_blobs = sqlite3.connect(utils.blobs_path)

all_ids = [row[0] for row in conn_blobs.execute('SELECT blob_id FROM blobs')]
print(f"Number of blobs in sqlite: {len(all_ids)}")

has_ids = []
for id in all_ids:
    folder, filename = utils.get_blob_filename(id)
    remote_path = os.path.join(folder, filename)
    if remote_path in all_keys:
        has_ids.append(id)
print(f"Number of has: {len(has_ids)}")

conn_blobs.execute('UPDATE blobs SET has = 0')
utils.mark_has(conn_blobs, has_ids)

conn_blobs.execute('UPDATE blobs SET n_wanted = 0')
conn_blobs.commit()
conn_blobs.close()
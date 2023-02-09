# After hugo build remove threads with only a single post as they are never used.
import os
import json
import shutil

hugo_threads_folder = '~/sh/data/threads'
hugo_public_folder = '~/sh/public'

with open(os.path.join(hugo_threads_folder, 'threads.json'), 'r') as f:
    threads = json.load(f)

for root, posts in threads.items():
    if len(posts) == 1:
        path = os.path.join(hugo_public_folder, f"threads/{root}")
        try:
            shutil.rmtree(path)
            print(path)
        except:
            print(f'No such file: {path}')

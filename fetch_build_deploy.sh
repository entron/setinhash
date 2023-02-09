#!/bin/bash
scp ssb:~/hugo.tar.gz /dev/shm/
cd /dev/shm/
tar xf hugo.tar.gz
cd hugo/
hugo

cp ~/prune_single_post_threads.py .
python3 prune_single_post_threads.py

cd /dev/shm
cp ~/public.tar.gz .
tar xf public.tar.gz
rsync -rvc --dry-run hugo/public/ public | head --lines=-3 | tail --lines=+2  > files2copy.txt 


tar czf public.tar.gz public/
cp public.tar.gz ~/

# rclone sync --size-only --fast-list public remote:www.setinhash.com
gsutil -m rsync -c -R public gs://www.setinhash.com
gcloud compute instances stop hugo

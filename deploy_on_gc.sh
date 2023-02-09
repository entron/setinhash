#!/bin/bash
tar czf hugo.tar.gz hugo/
gcloud compute instances start hugo
sleep 15s
gcloud compute ssh hugo --command="bash fetch_build_deploy.sh"
# The above script should stop hugo but in case error just add another stop to make sure
sleep 15s
gcloud compute instances stop hugo
**This project is exprimental.**

Setinhash converts content on the SSB network into a format that can be directly parsed by the fast static site engine, Hugo (https://gohugo.io/). In this example, I use Google Cloud Storage (https://cloud.google.com/storage/) to store the generated static site and DigitalOcean Spaces (https://www.digitalocean.com/products/spaces) to store blobs content, to save cost. I utilized the following resources:

A small VPS on DigitalOcean to run an SSB server and convert the SSB content to Hugo format every day. It also runs cron jobs to control the entire workflow.
A VPS with 16GB RAM on Google Cloud that only runs once or twice a day to build the static site using Hugo, and then sync the generated site to Google Cloud Storage.
Cloudflare in front of everything.
The current setup is designed with serving millions of pages and daily visits in mind, while minimizing cost.


## Setup Digitalocean vps and space

1. Install and run [ssb-pub](https://github.com/ahdinosaur/ssb-pub).

2. Install [PySecretHandshake](https://github.com/pferreir/PySecretHandshake) and [pyssb](https://github.com/pferreir/pyssb).

3. Clone this repo to the user home directory.

4. Create a hugo empty project in the home directory.

5. Copy the noteworthy folder in this repo to the themes folder in the generated hugo project 

6. Copy the config.toml file in this repo to replace the file in root directory of the hugo project.

7. Copy deploy_on_gc.sh in this repo to the user home directory.

8. Setup [gcloud CLI](https://cloud.google.com/sdk/gcloud) so that you can start and stop google cloud VPS below.

9. Create a digitalocean space for serving blobs content.

10. Add the following lines to the crontab

   ```
   0 * * * * cd /root/setinhash/ && python3 ssb2hugo.py >> cron.log 2>&1
   15 * * * * cd /root/setinhash/ && python3 upload_want_blobs.py  >> cron.log 2>&1
   10 6 * * * time bash deploy_on_gc.sh > deploy.log 2>&1 
   30 0 * * * cd /root/setinhash/ python3 follow_pubs.py >> follow_pubs.log 2>&1
   ```

   

## Setup google cloud VPS

1. Create a VPS with at least 16GB RAM and 2 cores. The VPS will sleep most of time to save the cost and will be woke up by the the digital ocean VPS once or twice per day.
2. Copy fetch_build_deploy.sh in this repo to the user home directory.
3. Install hugo 

```
wget https://github.com/gohugoio/hugo/releases/download/v0.93.0/hugo_extended_0.93.0_Linux-64bit.deb
sudo dpkg -i hugo_extended_0.93.0_Linux-64bit.deb
```


## How to (re-)generate all contents from scratch

0. Run 

```
bash clean.sh
```

1. Run 

```
python update_feed_info.py
```

2. Run

```
python ssb2hugo.py -i
```
Make sure you have enough RAM (>=8GB) while running this command.

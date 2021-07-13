from flask import Flask, render_template, request, redirect
import youtube_dl
import textwrap
import twitter
import pymongo
import json
import re
import os

app = Flask(__name__)
pathregex = re.compile("\\w{1,15}\\/status\\/\\d{19}")
discord_user_agents = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:38.0) Gecko/20100101 Firefox/38.0", "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"]

# Read config from config.json. If it does not exist, create new.
if not os.path.exists("config.json"):
    with open("config.json", "w") as outfile:
        default_config = {"config":{"link_cache":"json","database":"[url to mongo database goes here]","method":"youtube-dl"},"api":{"api_key":"[api_key goes here]","consumer_secret":"[api_secret goes here]","access_token":"[access_token goes here]","access_secret":"[access_secret goes here]"}}
        json.dump(default_config, outfile, indent=4, sort_keys=True)

    config = default_config
else:
    f = open("config.json")
    config = json.load(f)
    f.close()

if config['config']['method'] in ('api', 'hybrid'):
    auth = twitter.oauth.OAuth(config['api']['access_token'], config['api']['access_secret'], config['api']['api_key'], config['api']['api_secret'])
    twitter_api = twitter.Twitter(auth=auth)

link_cache_system = config['config']['link_cache']

if link_cache_system == "json":
    link_cache = {}
    if not os.path.exists("config.json"):
        with open("config.json", "w") as outfile:
            default_link_cache = {"test":"test"}
            json.dump(default_link_cache, outfile, indent=4, sort_keys=True)

    f = open('links.json',)
    link_cache = json.load(f)
    f.close()
elif link_cache_system == "db":
    client = pymongo.MongoClient(config['config']['database'], connect=False)
    db = client.TwitFix

@app.route('/')
def default():
    return render_template('default.html', message="TwitFix is an attempt to fix twitter video embeds in discord! created by Robin Universe :) 💖 ")

@app.route('/oembed.json')
def oembedend():
    desc = request.args.get("desc", None)
    user = request.args.get("user", None)
    link = request.args.get("link", None)
    return o_embed_gen(desc,user,link)

@app.route('/<path:subpath>')
def twitfix(sub_path):
    user_agent = request.headers.get('user-agent')
    match = pathregex.search(sub_path)
    if match is not None:
        twitter_url = sub_path

        if match.start() == 0:
            twitter_url = "https://twitter.com/" + sub_path

        if user_agent in discord_user_agents:
            res = embed_video(twitter_url)
            return res
        else:
            return redirect(twitter_url, 301)
    else:
        return redirect("https://twitter.com/" + sub_path, 301)

@app.route('/other/<path:subpath>') # Show all info that Youtube-DL can get about a video as a json
def other(sub_path):
    res = embed_video(sub_path)
    return res

@app.route('/info/<path:subpath>') # Show all info that Youtube-DL can get about a video as a json
def info(sub_path):
    with youtube_dl.YoutubeDL({'outtmpl': '%(id)s.%(ext)s'}) as ydl:
        result = ydl.extract_info(sub_path, download=False)

    return result

def embed_video(vidlink):
    cached_vnf = get_vnf_from_link_cache(vidlink)

    if cached_vnf == None:
        try:
            vnf = link_to_vnf(vidlink)
            add_vnf_to_link_cache(vidlink, vnf)
            return embed(vidlink, vnf)
        except Exception as e:
            print(e)
            return render_template('default.html', message="Failed to scan your link!")
    else:
        return embed(vidlink, cached_vnf)

def video_info(url, tweet="", desc="", thumb="", uploader=""): # Return a dict of video info with default values
    vnf = {
        "tweet"         :tweet,
        "url"           :url,
        "description"   :desc,
        "thumbnail"     :thumb,
        "uploader"      :uploader
    }
    return vnf

def link_to_vnf_from_api(vidlink):
    print("Attempting to download tweet info from Twitter API")
    twid = int(re.sub(r'\?.*$','',vidlink.rsplit("/", 1)[-1])) # gets the tweet ID as a int from the passed url
    tweet = twitter_api.statuses.show(_id=twid, tweet_mode="extended")
    if tweet['extended_entities']['media'][0]['video_info']['variants'][-1]['content_type'] == "video/mp4":
        url = tweet['extended_entities']['media'][0]['video_info']['variants'][-1]['url']
    else:
        url = tweet['extended_entities']['media'][0]['video_info']['variants'][-2]['url']

    if len(tweet['full_text']) > 200:
        text = textwrap.shorten(tweet['full_text'], width=200, placeholder="...")
    else:
        text = tweet['full_text']

    print(text)
    print(len(text))

    vnf = video_info(url, vidlink, text, tweet['extended_entities']['media'][0]['media_url'], tweet['user']['name'])
    return vnf

def link_to_vnf_from_youtubedl(vidlink):
    print("Attempting to download tweet info via YoutubeDL")
    with youtube_dl.YoutubeDL({'outtmpl': '%(id)s.%(ext)s'}) as ydl:
        result = ydl.extract_info(vidlink, download=False)
        vnf = video_info(result['url'], vidlink, result['description'].rsplit(' ',1)[0], result['thumbnail'], result['uploader'])
        return vnf

def link_to_vnf(vidlink): # Return a VideoInfo object or die trying
    if config['config']['method'] == 'hybrid':
        try:
            return link_to_vnf_from_api(vidlink)
        except Exception as e:
            print("API Failed")
            print(e)
            return link_to_vnf_from_youtubedl(vidlink)
    elif config['config']['method'] == 'api':
        try:
            return link_to_vnf_from_api(vidlink)
        except Exception as e:
            print("API Failed")
            print(e)
            return None
    elif config['config']['method'] == 'youtube-dl':
        try:
            return link_to_vnf_from_youtubedl(vidlink)
        except Exception as e:
            print("Youtube-DL Failed")
            print(e)
            return None
    else:
        print("Please set the method key in your config file to 'api' 'youtube-dl' or 'hybrid'")
        return None


def get_vnf_from_link_cache(video_link):
    if link_cache_system == "db":
        collection = db.linkCache
        vnf = collection.find_one({'tweet': video_link})
        if vnf != None: 
            print("Link located in DB cache")
            return vnf
        else:
            print("Link not in DB cache")
            return None
    elif link_cache_system == "json":
        if video_link in link_cache:
            print("Link located in json cache")
            vnf = link_cache[video_link]
            return vnf
        else:
            print("Link not in json cache")
            return None

def add_vnf_to_link_cache(video_link, vnf):
    if link_cache_system == "db":
        try:
            out = db.linkCache.insert_one(vnf)
            print("Link added to DB cache")
            return True
        except Exception:
            print("Failed to add link to DB cache")
            return None
    elif link_cache_system == "json":
        link_cache[video_link] = vnf
        with open("links.json", "w") as outfile: 
            json.dump(link_cache, outfile, indent=4, sort_keys=True)
            return None

def embed(vidlink, vnf):
    desc = re.sub(r' http.*t\.co\S+', '', vnf['description'].replace("#","＃"))
    return render_template('index.html', vidurl=vnf['url'], desc=desc, pic=vnf['thumbnail'], user=vnf['uploader'], vidlink=vidlink)

def o_embed_gen(description, user, vidlink):
    out = {
            "type":"video",
            "version":"1.0",
            "provider_name":"TwitFix",
            "provider_url":"https://github.com/robinuniverse/twitfix",
            "title":description,
            "author_name":user,
            "author_url":vidlink
            }

    return out

if __name__ == "__main__":
    app.run(host='0.0.0.0')

from weakref import finalize
from flask import Flask, render_template, request, redirect, abort, Response, send_from_directory, url_for, send_file, make_response, jsonify
from flask_cors import CORS
import textwrap
import re
import os
import urllib.parse
import urllib.request
import combineImg
from datetime import date,datetime, timedelta
from io import BytesIO
import msgs
import twExtract as twExtract
from configHandler import config
from cache import addVnfToLinkCache,getVnfFromLinkCache
from yt_dlp.utils import ExtractorError
app = Flask(__name__)
CORS(app)

pathregex = re.compile("\\w{1,15}\\/(status|statuses)\\/\\d{2,20}")
generate_embed_user_agents = [
    "facebookexternalhit/1.1",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.57 Safari/537.36",
    "Mozilla/5.0 (Windows; U; Windows NT 10.0; en-US; Valve Steam Client/default/1596241936; ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36",
    "Mozilla/5.0 (Windows; U; Windows NT 10.0; en-US; Valve Steam Client/default/0; ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36", 
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_1) AppleWebKit/601.2.4 (KHTML, like Gecko) Version/9.0.1 Safari/601.2.4 facebookexternalhit/1.1 Facebot Twitterbot/1.0", 
    "facebookexternalhit/1.1",
    "Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; Valve Steam FriendsUI Tenfoot/0; ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.105 Safari/537.36", 
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)", 
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:38.0) Gecko/20100101 Firefox/38.0", 
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)", 
    "TelegramBot (like TwitterBot)", 
    "Mozilla/5.0 (compatible; January/1.0; +https://gitlab.insrt.uk/revolt/january)", 
    "test"]

@app.route('/') # If the useragent is discord, return the embed, if not, redirect to configured repo directly
def default():
    user_agent = request.headers.get('user-agent')
    if user_agent in generate_embed_user_agents:
        return message("TwitFix is an attempt to fix twitter video embeds in discord! created by Robin Universe :)\n\n💖\n\nClick me to be redirected to the repo!")
    else:
        return redirect(config['config']['repo'], 301)

@app.route('/oembed.json') #oEmbed endpoint
def oembedend():
    desc  = request.args.get("desc", None)
    user  = request.args.get("user", None)
    link  = request.args.get("link", None)
    ttype = request.args.get("ttype", None)
    return  oEmbedGen(desc, user, link, ttype)

@app.route('/<path:sub_path>') # Default endpoint used by everything
def twitfix(sub_path):
    user_agent = request.headers.get('user-agent')
    match = pathregex.search(sub_path)

    if request.url.startswith("https://d.vx"): # Matches d.fx? Try to give the user a direct link
        if match.start() == 0:
            twitter_url = "https://twitter.com/" + sub_path
        if user_agent in generate_embed_user_agents:
            print( " ➤ [ D ] d.vx link shown to discord user-agent!")
            if request.url.endswith(".mp4") and "?" not in request.url:
                
                if "?" not in request.url:
                    clean = twitter_url[:-4]
                else:
                    clean = twitter_url

                vnf,e = vnfFromCacheOrDL(clean)
                if vnf == None or vnf['images'][0] == {}:
                    if e is not None:
                        return message(msgs.failedToScan+msgs.failedToScanExtra+e)
                    return message(msgs.failedToScan)
                
                return getTemplate("rawvideo.html",vnf,vnf['images'][0],"","",clean,"","","","")
            else:
                return message("To use a direct MP4 link in discord, remove anything past '?' and put '.mp4' at the end")
        else:
            print(" ➤ [ R ] Redirect to MP4 using d.fxtwitter.com")
            return dir(sub_path)
    elif request.url.startswith("https://c.vx"):
        twitter_url = sub_path

        if match.start() == 0:
            twitter_url = "https://twitter.com/" + sub_path
        
        if user_agent in generate_embed_user_agents:
            return embedCombined(twitter_url)
        else:
            print(" ➤ [ R ] Redirect to " + twitter_url)
            return redirect(twitter_url, 301)
    elif request.url.endswith(".mp4") or request.url.endswith("%2Emp4"):
        twitter_url = "https://twitter.com/" + sub_path
        
        if "?" not in request.url:
            clean = twitter_url[:-4]
        else:
            clean = twitter_url
            
        vnf,e = vnfFromCacheOrDL(clean)
        if vnf == None or vnf['images'][0] == {}:
            if e is not None:
                return message(msgs.failedToScan+msgs.failedToScanExtra+e)
            return message(msgs.failedToScan)
        return getTemplate("rawvideo.html",vnf,vnf['images'][0],"","",clean,"","","","")

    elif request.url.endswith("/1") or request.url.endswith("/2") or request.url.endswith("/3") or request.url.endswith("/4") or request.url.endswith("%2F1") or request.url.endswith("%2F2") or request.url.endswith("%2F3") or request.url.endswith("%2F4"):
        twitter_url = "https://twitter.com/" + sub_path
        
        if "?" not in request.url:
            clean = twitter_url[:-2]
        else:
            clean = twitter_url

        image = ( int(request.url[-1]) - 1 )
        return embed_video(clean, image)

    if match is not None:
        twitter_url = sub_path

        if match.start() == 0:
            twitter_url = "https://twitter.com/" + sub_path

        if user_agent in generate_embed_user_agents:
            res = embed_video(twitter_url)
            return res

        else:
            print(" ➤ [ R ] Redirect to " + twitter_url)
            return redirect(twitter_url, 301)
    else:
        return message("This doesn't appear to be a twitter URL")

        
@app.route('/dir/<path:sub_path>') # Try to return a direct link to the MP4 on twitters servers
def dir(sub_path):
    user_agent = request.headers.get('user-agent')
    url   = sub_path
    match = pathregex.search(url)
    if match is not None:
        twitter_url = url

        if match.start() == 0:
            twitter_url = "https://twitter.com/" + url

        if user_agent in generate_embed_user_agents:
            res = embed_video(twitter_url)
            return res

        else:
            print(" ➤ [ R ] Redirect to direct MP4 URL")
            return direct_video(twitter_url)
    else:
        return redirect(url, 301)

@app.route('/favicon.ico')
def favicon(): # pragma: no cover
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico',mimetype='image/vnd.microsoft.icon')

@app.route("/rendercombined.jpg")
def rendercombined():
    # get "imgs" from request arguments
    imgs = request.args.get("imgs", "")

    if 'combination_method' in config['config'] and config['config']['combination_method'] != "local":
        url = config['config']['combination_method'] + "/rendercombined.jpg?imgs=" + imgs
        return redirect(url, 302)
    # Redirecting here instead of setting the embed URL directly to this because if the config combination_method changes in the future, old URLs will still work

    imgs = imgs.split(",")
    if (len(imgs) == 0 or len(imgs)>4):
        abort(400)
    #check that each image starts with "https://pbs.twimg.com"
    for img in imgs:
        if not img.startswith("https://pbs.twimg.com"):
            abort(400)
    finalImg= combineImg.genImageFromURL(imgs)
    imgIo = BytesIO()
    finalImg = finalImg.convert("RGB")
    finalImg.save(imgIo, 'JPEG',quality=70)
    imgIo.seek(0)
    return send_file(imgIo, mimetype='image/jpeg')

def upgradeVNF(vnf):
    # Makes sure any VNF object passed through this has proper fields if they're added in later versions
    if 'verified' not in vnf:
        vnf['verified']=False
    if 'size' not in vnf:
        if vnf['type'] == 'Video':
            vnf['size']={'width':720,'height':480}
        else:
            vnf['size']={}

    if vnf["type"] != "Text" and type(vnf['images'][0] is not dict):
        if vnf["type"] == "Image":
            if (vnf['images'][4] == ''):
                mediaCount = 0
            else:
                mediaCount = int(vnf['images'][4])
            for i in range(mediaCount):
                if vnf['images'][i] == '':
                    vnf['images'][i] = {}
                elif vnf['type'] == 'Video':
                    vnf['images'][i]={'url':vnf['images'][i],'type':'Video','thumb':vnf['thumbnail']}
                elif vnf['type'] == 'Image':
                    vnf['images'][i]={'url':vnf['images'][i],'type':'Image'}
        elif vnf["type"] == "Video":
            vnf['images']=[{'url':vnf['url'],'type':'Video','thumb':vnf['thumbnail']},{},{},{},'1']
        vnf["type"] = "Multi"

    if 'qrtURL' not in vnf:
        if vnf['qrt'] == {}:
            vnf['qrtURL'] = None
        else: # 
            vnf['qrtURL'] = f"https://twitter.com/{vnf['qrt']['screen_name']}/status/{vnf['qrt']['id']}"
    return vnf

def getDefaultTTL(): # TTL for deleting items from the database
    return datetime.today().replace(microsecond=0) + timedelta(days=1)

def vnfFromCacheOrDL(video_link):
    cached_vnf = getVnfFromLinkCache(video_link)
    if cached_vnf == None:
        try:
            vnf = link_to_vnf(video_link)
            addVnfToLinkCache(video_link, vnf)
            return vnf,None
        except (ExtractorError, twExtract.twExtractError.TwExtractError) as exErr:
            if 'HTTP Error 404' in exErr.msg or 'No status found with that ID' in exErr.msg:
                exErr.msg=msgs.tweetNotFound
            elif 'suspended' in exErr.msg:
                exErr.msg=msgs.tweetSuspended
            else:
                exErr.msg=None
            return None,exErr.msg
        except Exception as e:
            print(e)
            return None,None
    else:
        print("cached_vnf: " + str(cached_vnf))
        return upgradeVNF(cached_vnf),None

def direct_video(video_link): # Just get a redirect to a MP4 link from any tweet link
    vnf,e = vnfFromCacheOrDL(video_link)
    if vnf != None:
        return redirect(vnf['url'], 301)
    else:
        if e is not None:
            return message(msgs.failedToScan+msgs.failedToScanExtra+e)
        return message(msgs.failedToScan)

def direct_video_link(video_link): # Just get a redirect to a MP4 link from any tweet link
    vnf,e = vnfFromCacheOrDL(video_link)
    if vnf != None:
        return vnf['url']
    else:
        if e is not None:
            return message(msgs.failedToScan+msgs.failedToScanExtra+e)
        return message(msgs.failedToScan)

def embed_video(video_link, image=0): # Return Embed from any tweet link
    vnf,e = vnfFromCacheOrDL(video_link)

    if vnf != None:
        return embed(video_link, vnf, image)
    else:
        if e is not None:
            return message(msgs.failedToScan+msgs.failedToScanExtra+e)
        return message(msgs.failedToScan)

def tweetInfo(tweet="", desc="", thumb="", uploader="", screen_name="", pfp="", tweetType="", images="", hits=0, likes=0, rts=0, time="", qrtURL="", nsfw=False,ttl=None,verified=False,size={},poll=None): # Return a dict of video info with default values
    if (ttl==None):
        ttl = getDefaultTTL()
    if images[4] != "":
        type="Multi"
    else:
        type="Text"
    vnf = {
        "tweet"         : tweet,
        "description"   : desc,
        "uploader"      : uploader,
        "screen_name"   : screen_name,
        "pfp"           : pfp,
        "type"          : type,
        "images"        : images,
        "hits"          : hits,
        "likes"         : likes,
        "rts"           : rts,
        "time"          : time,
        "qrtURL"        : qrtURL,
        "nsfw"          : nsfw,
        "ttl"           : ttl,
        "verified"      : verified,
        "size"          : size,
        "poll"          : poll
    }
    if (poll is None):
        del vnf['poll']
    return vnf

def genMediaObject(apiMedia):
    type = mediaType(apiMedia)
    if type == "Video":
        mediaObj = {"type":type,"url":""}
        if apiMedia['video_info']['variants']:
            best_bitrate = -1
            mediaObj["thumb"] = apiMedia['media_url_https']
            mediaObj["size"] = apiMedia["original_info"]
            for video in apiMedia['video_info']['variants']:
                if video['content_type'] == "video/mp4" and video['bitrate'] > best_bitrate:
                    mediaObj["url"] = video['url']
                    best_bitrate = video['bitrate']
    elif type == "Image":
        mediaObj = {"type":type,"url":apiMedia['media_url_https']}
    return mediaObj


def link_to_vnf_from_tweet_data(tweet,video_link,mediaIndex=0):
    media = [{},{},{},{}, ""]
    # Check to see if tweet has a video, if not, make the url passed to the VNF the first t.co link in the tweet
    if 'extended_entities' in tweet: # text tweet:
        media = [{},{},{},{}, ""]
        i = 0
        for twtmedia in tweet['extended_entities']['media']:
            media[i] = genMediaObject(twtmedia)
            i = i + 1

        media[4] = str(i)

    qrtURL = None
    if 'quoted_status' in tweet and 'quoted_status_permalink' in tweet:
        qrtURL = tweet['quoted_status_permalink']['expanded']

    text = tweet['full_text']

    if 'possibly_sensitive' in tweet:
        nsfw = tweet['possibly_sensitive']
    else:
        nsfw = False

    if 'entities' in tweet and 'urls' in tweet['entities']:
        for eurl in tweet['entities']['urls']:
            if "/status/" in eurl["expanded_url"] and eurl["expanded_url"].startswith("https://twitter.com/"):
                text = text.replace(eurl["url"], "")
            else:
                text = text.replace(eurl["url"],eurl["expanded_url"])
    ttl = None #default

    if 'card' in tweet and tweet['card']['name'].startswith('poll'):
        poll=getPollObject(tweet['card'])
        if tweet['card']['binding_values']['counts_are_final']['boolean_value'] == False:
            ttl = datetime.today().replace(microsecond=0) + timedelta(minutes=1)
    else:
        poll=None

    vnf = tweetInfo(
        video_link, 
        text,
        tweet['user']['name'], 
        tweet['user']['screen_name'], 
        tweet['user']['profile_image_url'],
        likes=tweet['favorite_count'], 
        rts=tweet['retweet_count'], 
        time=tweet['created_at'], 
        qrtURL=qrtURL, 
        images=media,
        nsfw=nsfw,
        verified=tweet['user']['verified'],
        size={},
        poll=poll,
        ttl=ttl
    )
        
    return vnf


def link_to_vnf_from_unofficial_api(video_link):
    tweet=None
    print(" ➤ [ + ] Attempting to download tweet info from UNOFFICIAL Twitter API")
    tweet = twExtract.extractStatus(video_link)
    print (" ➤ [ ✔ ] Unofficial API Success")
    return link_to_vnf_from_tweet_data(tweet,video_link)

def link_to_vnf(video_link): # Return a VideoInfo object or die trying
    return link_to_vnf_from_unofficial_api(video_link)

def message(text):
    return render_template(
        'default.html', 
        message = text, 
        color   = config['config']['color'], 
        appname = config['config']['appname'], 
        repo    = config['config']['repo'], 
        url     = config['config']['url'] )

def getTemplate(template,vnf,media,desc,image,video_link,color,urlDesc,urlUser,urlLink,appNameSuffix="",embedVNF=None):
    if (embedVNF is None):
        embedVNF = vnf
    if ('width' in embedVNF['size'] and 'height' in embedVNF['size']):
        embedVNF['size']['width'] = min(embedVNF['size']['width'],2000)
        embedVNF['size']['height'] = min(embedVNF['size']['height'],2000)

    url = ''
    thumb=''
    print("med: "+str(media))
    if (vnf["type"] != "Text"):
        if (media['type'] == "Video"):
            url = media['url']
            thumb = media['thumb']
        elif (media['type'] == "Image"):
            image = media['url']
            url = media['url']

    return render_template(
        template, 
        likes      = vnf['likes'], 
        rts        = vnf['rts'], 
        time       = vnf['time'], 
        screenName = vnf['screen_name'], 
        vidlink    = embedVNF['url'], 
        pfp        = vnf['pfp'],  
        vidurl     = embedVNF['url'], 
        desc       = desc,
        pic        = image,
        user       = vnf['uploader'], 
        video_link = vnf, 
        color      = color, 
        appname    = config['config']['appname'] + appNameSuffix, 
        repo       = config['config']['repo'], 
        url        = config['config']['url'], 
        urlDesc    = urlDesc, 
        urlUser    = urlUser, 
        urlLink    = urlLink,
        tweetLink  = vnf['tweet'],
        videoSize  = embedVNF['size'] )

def embed(video_link, vnf, image):
    print(" ➤ [ E ] Embedding " + vnf['type'] + ": " + video_link)
    
    desc    = re.sub(r' http.*t\.co\S+', '', vnf['description'])
    urlUser = urllib.parse.quote(vnf['uploader'])
    urlDesc = urllib.parse.quote(desc)
    urlLink = urllib.parse.quote(video_link)
    likeDisplay = msgs.genLikesDisplay(vnf)
    
    if 'poll' in vnf:
        pollDisplay= msgs.genPollDisplay(vnf['poll'])
    else:
        pollDisplay=""

    qrt=None
    if vnf['qrtURL'] is not None:
        qrt,e=vnfFromCacheOrDL(vnf['qrtURL'])
        if qrt is not None:
            desc=msgs.formatEmbedDesc(vnf['type'],desc,qrt,pollDisplay,likeDisplay)
    embedVNF=None
    appNamePost = ""
    if vnf['type'] == "Text": # Change the template based on tweet type
        template = 'text.html'
        media={}
    if vnf['type'] == "Multi":
        if qrt is not None and qrt['type'] != "Text":
            embedVNF=qrt
            if qrt['type'] == "Image":
                if embedVNF['images'][4]!="1":
                    appNamePost = " - Image " + str(image+1) + "/" + str(vnf['images'][4])
                image = embedVNF['images'][image]
                template = 'image.html'
            elif qrt['type'] == "Video" or qrt['type'] == "":
                urlDesc = urllib.parse.quote(textwrap.shorten(desc, width=220, placeholder="..."))
                template = 'video.html'
            
    if vnf['type'] == "Image":
        if vnf['images'][4]!="1":
            appNamePost = " - Media " + str(image+1) + "/" + str(vnf['images'][4])
        media = vnf['images'][image]
        print("embed: "+str(media))
        if media['type'] == "Image":
            template = 'image.html'
        elif media['type'] == "Video":
            template = 'video.html'
            urlDesc = urllib.parse.quote(textwrap.shorten(desc, width=220, placeholder="..."))
        
    color = "#7FFFD4" # Green

    if vnf['nsfw'] == True:
        color = "#800020" # Red
    
    return getTemplate(template,vnf,media,desc,image,video_link,color,urlDesc,urlUser,urlLink,appNamePost,embedVNF)


def embedCombined(video_link):
    vnf,e = vnfFromCacheOrDL(video_link)

    if vnf != None:
        return embedCombinedVnf(video_link, vnf)
    else:
        if e is not None:
            return message(msgs.failedToScan+msgs.failedToScanExtra+e)
        return message(msgs.failedToScan)

def embedCombinedVnf(video_link,vnf):
    if vnf['type'] != "Image" or vnf['images'][4] == "1":
        return embed(video_link, vnf, 0)
    desc    = re.sub(r' http.*t\.co\S+', '', vnf['description'])
    urlUser = urllib.parse.quote(vnf['uploader'])
    urlDesc = urllib.parse.quote(desc)
    urlLink = urllib.parse.quote(video_link)
    likeDisplay = msgs.genLikesDisplay(vnf)

    if 'poll' in vnf:
        pollDisplay= msgs.genPollDisplay(vnf['poll'])
    else:
        pollDisplay=""

    qrt=None
    if vnf['qrtURL'] is not None:
        qrt,e=vnfFromCacheOrDL(vnf['qrtURL'])
        if qrt is not None:
            desc=msgs.formatEmbedDesc(vnf['type'],desc,qrt,pollDisplay,likeDisplay)

    
    image = "https://vxtwitter.com/rendercombined.jpg?imgs="
    for i in range(0,int(vnf['images'][4])):
        image = image + vnf['images'][i] + ","
    image = image[:-1] # Remove last comma

    color = "#7FFFD4" # Green

    if vnf['nsfw'] == True:
        color = "#800020" # Red
    return getTemplate('image.html',vnf,{'todo':'todo'},desc,image,video_link,color,urlDesc,urlUser,urlLink,appNameSuffix=" - View original tweet for full quality")


def getPollObject(card):
    poll={"total_votes":0,"choices":[]}
    choiceCount=0
    if (card["name"]=="poll2choice_text_only"):
        choiceCount=2
    elif (card["name"]=="poll3choice_text_only"):
        choiceCount=3
    elif (card["name"]=="poll4choice_text_only"):
        choiceCount=4
    
    for i in range(0,choiceCount):
        choice = {"text":card["binding_values"][f"choice{i+1}_label"]["string_value"],"votes":int(card["binding_values"][f"choice{i+1}_count"]["string_value"])}
        poll["total_votes"]+=choice["votes"]
        poll["choices"].append(choice)
    # update each choice with a percentage
    for choice in poll["choices"]:
        choice["percent"] = round((choice["votes"]/poll["total_votes"])*100,1)

    return poll


def mediaType(media): # Are we dealing with a Video, Image, or Text tweet?
    if 'video_info' in media:
        out = "Video"
    else:
        out = "Image"

    return out


def oEmbedGen(description, user, video_link, ttype):
    out = {
            "type"          : ttype,
            "version"       : "1.0",
            "provider_name" : config['config']['appname'],
            "provider_url"  : config['config']['repo'],
            "title"         : description,
            "author_name"   : user,
            "author_url"    : video_link
            }

    return out

if __name__ == "__main__":
    app.config['SERVER_NAME']='localhost:80'
    app.run(host='0.0.0.0')

# -*- coding: utf-8 -*-
"""
A Kodi plugin for Viaplay
"""
import sys
import os
import cookielib
import urllib
import urlparse
from datetime import datetime, date
import dateutil.parser
from dateutil import tz
import time
import re
import json
import requests
import uuid
from collections import defaultdict
import HTMLParser

import xbmc
import xbmcaddon
import xbmcvfs
import xbmcgui
import xbmcplugin

addon = xbmcaddon.Addon()
addon_path = xbmc.translatePath(addon.getAddonInfo('path'))
addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))
language = addon.getLocalizedString
logging_prefix = '[%s-%s]' % (addon.getAddonInfo('id'), addon.getAddonInfo('version'))

if not xbmcvfs.exists(addon_profile):
    xbmcvfs.mkdir(addon_profile)

# Get the plugin url in plugin:// notation.
_url = sys.argv[0]
# Get the plugin handle as an integer number.
_handle = int(sys.argv[1])

http_session = requests.Session()
cookie_file = os.path.join(addon_profile, 'viaplay_cookies')
cookie_jar = cookielib.LWPCookieJar(cookie_file)
try:
    cookie_jar.load(ignore_discard=True, ignore_expires=True)
except IOError:
    pass
http_session.cookies = cookie_jar
    
username = addon.getSetting('email')
password = addon.getSetting('password')
subdict = defaultdict(list)

if addon.getSetting('debug') == 'false':
    debug = False
else:
    debug = True
    
if addon.getSetting('subtitles') == 'false':
    subtitles = False
else:
    subtitles = True
    
if addon.getSetting('country') == '0':
    country = 'se'
elif addon.getSetting('country') == '1':
    country = 'dk'
elif addon.getSetting('country') == '2':
    country = 'no'
else:
    country = 'fi'
    
base_url = 'http://content.viaplay.' + country + '/pc-' + country
    
def addon_log(string):
    if debug:
        xbmc.log("%s: %s" %(logging_prefix, string))
               
def url_parser(url):
    """Sometimes, Viaplay adds some weird templated stuff to the end of the URL.
    Example: https://content.viaplay.se/androiddash-se/serier{?dtg}"""
    url = url.replace('https', 'http') # http://forum.kodi.tv/showthread.php?tid=270336
    parsed_url = re.match('[^{]+', url).group()
    return parsed_url
                     
def make_request(url, method, payload=None, headers=None):
    """Make an HTTP request. Return the response as JSON."""
    addon_log('Original URL: %s' % url)
    addon_log('Request & parsed URL: %s' % url_parser(url))
    if method == 'get':
        req = http_session.get(url_parser(url), params=payload, headers=headers, allow_redirects=False, verify=False)
    else:
        req = http_session.post(url_parser(url), data=payload, headers=headers, allow_redirects=False, verify=False)
    addon_log('Response code: %s' % req.status_code)
    addon_log('Response: %s' % req.content)
    cookie_jar.save(ignore_discard=True, ignore_expires=False)
    return json.loads(req.content)
   
def login(username, password):
    """Login to Viaplay. Return True/False based on the result."""
    url = 'http://login.viaplay.' + country + '/api/login/v1'
    payload = {
    'deviceKey': 'atv-se',
    'username': username,
    'password': password,
    'persistent': 'true'
    }
    data = make_request(url=url, method='get', payload=payload)
    if data['success'] is False:
        return False
    else:
        return True
        
def validate_session():
    """Check if our session cookies are still valid."""
    url = 'http://login.viaplay.' + country + '/api/persistentLogin/v1'
    payload = {
        'deviceKey': 'atv-se'
    }
    data = make_request(url=url, method='get', payload=payload)
    if data['success'] is False:
        return False
    else:
        return True
        
def check_loginstatus(data):
    try:
        if data['name'] == 'MissingSessionCookieError':
            session = validate_session()
            if session is False:
                login_success = login(username, password)
            else:
                login_success = True
        else:
            login_success = True
    except KeyError:
        login_success = True
    return login_success

def get_streams(guid):
    """Return the URL for a stream. Append all available SAMI subtitle URL:s in the dict subguid."""
    url = 'http://play.viaplay.' + country + '/api/stream/byguid'
    payload = {
    'deviceId': uuid.uuid4(),
    'deviceName': 'atv',
    'deviceType': 'atv',
    'userAgent': 'AppleTV/2.4',
    'deviceKey': 'atv-se',
    'guid': guid
    }

    data = make_request(url=url, method='get', payload=payload)
    login_status = check_loginstatus(data)
    if login_status is True:
        try:
            m3u8_url = data['_links']['viaplay:playlist']['href']
            status = True
        except KeyError:
            # we might have to request the stream again after logging in
            if data['name'] == 'MissingSessionCookieError':
                data = make_request(url=url, method='get', payload=payload)
            try:
                m3u8_url = data['_links']['viaplay:playlist']['href']
                status = True
            except KeyError:
                if data['success'] is False:
                    status = data['message']
        if status is True:
            if subtitles:
                try:
                    subtitle_urls = data['_links']['viaplay:sami']
                    for sub in subtitle_urls:
                        suburl = sub['href']
                        subdict[guid].append(suburl)
                except KeyError:
                    addon_log('No subtitles found for guid %s' % guid)
            return m3u8_url
        else:
            dialog = xbmcgui.Dialog()
            dialog.ok(language(30005),
            status)
            return False
    else:
        dialog = xbmcgui.Dialog()
        dialog.ok(language(30005),
        language(30006))
        return False
         
def get_categories(url):
    data = make_request(url=url, method='get')
    pageType = data['pageType']
    try:
        sectionType = data['sectionType']
    except:
        sectionType = None
    addon_log('pageType: %s' % pageType)
    addon_log('sectionType: %s' % sectionType)
    if sectionType == 'sportPerDay':
        categories = data['_links']['viaplay:days']
    elif pageType == 'root':
        categories = data['_links']['viaplay:sections']
    elif pageType == 'section':
        categories = data['_links']['viaplay:categoryFilters']
    return categories
    
def root_menu(url):
    categories = get_categories(url)
    listing = []
    
    for category in categories:
        categorytype = category['type']
        videotype = category['name']
        title = category['title']
        if categorytype == 'vod':
            list_item = xbmcgui.ListItem(label=title)
            list_item.setProperty('IsPlayable', 'false')
            list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
            list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
            if videotype == 'series':
                parameters = {'action': 'series', 'url': category['href']}
            elif videotype == 'movie':
                parameters = {'action': 'movie', 'url': category['href']}
            elif videotype == 'sport':
                parameters = {'action': 'sport', 'url': category['href']}
            elif videotype == 'kids':
                parameters = {'action': 'kids', 'url': category['href']}
            recursive_url = _url + '?' + urllib.urlencode(parameters)
            is_folder = True
            listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.endOfDirectory(_handle)
    
def movie_menu(url):
    categories = get_categories(url)
    listing = []
    
    for category in categories:
        title = category['title']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        parameters = {'action': 'sortby', 'url': category['href']}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.endOfDirectory(_handle)
    
def series_menu(url):
    categories = get_categories(url)
    listing = []
    
    for category in categories:
        title = category['title']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        parameters = {'action': 'sortby', 'url': category['href']}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.endOfDirectory(_handle)
    
def kids_menu(url):
    categories = get_categories(url)
    listing = []
    
    for category in categories:
        title = category['group']['title'].title() + ': ' + category['title']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        parameters = {'action': 'listproducts', 'url': category['href']}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.endOfDirectory(_handle)
    
def get_available_characters(url):
    characters = []
    data = make_request(url=url, method='get')
    
    for item in data['_embedded']['viaplay:products']:
        if not item['group'] in characters:
            characters.append(item['group'])
    return characters
       
def get_sortings(url):
    data = make_request(url=url, method='get')
    sorttypes = data['_links']['viaplay:sortings']
    return sorttypes
     
def sort_by(url):
    sortings = get_sortings(url)
    listing = []
    
    for sorting in sortings:
        title = sorting['title']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        try:
            if sorting['id'] == 'alphabetical':
                parameters = {'action': 'listalphabetical', 'url': sorting['href']}
            else:
                parameters = {'action': 'listproducts', 'url': sorting['href']}
        except TypeError:
            parameters = {'action': 'listproducts', 'url': sorting['href']}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        listing.append((recursive_url, list_item, is_folder))
        
    list_all_item = xbmcgui.ListItem(label=language(30013))
    list_all_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
    list_all_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
    # show all products in alphabetical order
    parameters = {'action': 'listproducts', 'url': url + '?sort=alphabetical'}
    recursive_url = _url + '?' + urllib.urlencode(parameters)
    is_folder = True
    
    xbmcplugin.addDirectoryItem(_handle, recursive_url, list_all_item, is_folder)
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.endOfDirectory(_handle)
    
def get_characters(url):
    characters = []
    products = get_products(make_request(url=url, method='get'))
    for item in products:
        character = item['group']
        if not character in characters:
            characters.append(item['group'])
    return characters
    
def alphabetical_menu(url):
    url = url_parser(url) # needed to get rid of {&letter}
    characters = get_characters(url)
    listing = []
    
    for character in characters:
        title = character.encode('utf-8')
        if character == '0-9':
            # 0-9 needs to be sent as a URL-encoded pound-sign
            letter = '%23'.encode('utf-8')
        else:
            letter = title.lower()
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        parameters = {'action': 'listproducts', 'url': url + '&letter=' + letter}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.endOfDirectory(_handle)
    
def next_page(data):
    """Return next page if the current page is less than the total page count."""
    try:
        currentPage = data['_embedded']['viaplay:blocks'][0]['currentPage']
        pageCount = data['_embedded']['viaplay:blocks'][0]['pageCount']
    except:
        currentPage = data['currentPage']
        pageCount = data['pageCount']
    if pageCount > currentPage:
        try:
            return data['_embedded']['viaplay:blocks'][0]['_links']['next']['href']
        except:
            return data['_links']['next']['href']
    
def list_products(url, *display):
    data = make_request(url=url, method='get')
    products = get_products(data)
    listing = []
    sort = None
    list_next_page = next_page(data)
    
    for item in products:
        type = item['type']
        try:
            playid = item['system']['guid']
            streamtype = 'guid'
        except KeyError:
            """The guid is not always available from the category listing.
            Send the self URL and let play_video grab the guid from there instead
            as it always provides more detailed data about each product."""
            playid = item['_links']['self']['href']
            streamtype = 'url'
        parameters = {'action': 'play', 'playid': playid, 'streamtype': streamtype}
        recursive_url = _url + '?' + urllib.urlencode(parameters)

        if type == 'episode':
            title = item['content']['series']['episodeTitle']
            is_folder = False
            is_playable = 'true'
            list_item = xbmcgui.ListItem(label=title)
            list_item.setProperty('IsPlayable', is_playable)
            list_item.setInfo('video', item_information(item))
            list_item.setArt(art(item))
            listing.append((recursive_url, list_item, is_folder))
            
        if type == 'sport':
            local_tz = tz.tzlocal()
            startdate_utc = dateutil.parser.parse(item['epg']['start'])
            startdate_local = startdate_utc.astimezone(local_tz)
            status = sports_status(item)
            if status == 'archive':
                title = 'Archive: ' + item['content']['title'].encode('utf-8')
                is_playable = 'true'
            else:
                title = item['content']['title'].encode('utf-8') + ' (' + startdate_local.strftime("%H:%M") + ')'
                is_playable = 'true'
            is_folder = False
            list_item = xbmcgui.ListItem(label=title)
            list_item.setProperty('IsPlayable', is_playable)
            list_item.setInfo('video', item_information(item))
            list_item.setArt(art(item))
            if 'live' in display:
                if status == 'live':
                    listing.append((recursive_url, list_item, is_folder))
            elif 'upcoming' in display:
                if status == 'upcoming':
                    listing.append((recursive_url, list_item, is_folder))
            elif 'archive' in display:
                if status == 'archive':
                    listing.append((recursive_url, list_item, is_folder))
            else:
                listing.append((recursive_url, list_item, is_folder))
            
        elif type == 'movie':
            title = item['content']['title'].encode('utf-8') + ' ' + '(' + str(item['content']['production']['year']) + ')'
            is_folder = False
            is_playable = 'true'
            list_item = xbmcgui.ListItem(label=title)
            list_item.setProperty('IsPlayable', is_playable)
            list_item.setInfo('video', item_information(item))
            list_item.setArt(art(item))
            listing.append((recursive_url, list_item, is_folder))
            
        elif type == 'series':
            title = item['content']['series']['title'].encode('utf-8')      
            self_url = item['_links']['viaplay:page']['href']
            parameters = {'action': 'seasons', 'url': self_url}
            recursive_url = _url + '?' + urllib.urlencode(parameters)
            is_folder = True
            is_playable = 'false'
            list_item = xbmcgui.ListItem(label=title)
            list_item.setProperty('IsPlayable', is_playable)
            list_item.setInfo('video', item_information(item))
            list_item.setArt(art(item))
            listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    if sort is True:
        xbmcplugin.addSortMethod(_handle, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    if list_next_page is not None:
        list_nextpage = xbmcgui.ListItem(label='Next Page')
        parameters = {'action': 'nextpage', 'url': list_next_page}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        xbmcplugin.addDirectoryItem(_handle, recursive_url, list_nextpage, is_folder)
    # xbmc.executebuiltin("Container.SetViewMode(500)") - force media view
    xbmcplugin.endOfDirectory(_handle)
    
def get_products(data):
    if data['type'] == 'season-list' or data['type'] == 'list':
        products = data['_embedded']['viaplay:products']
    elif data['type'] == 'product':
        products = data['_embedded']['viaplay:product']
    else:
        try:
            products = data['_embedded']['viaplay:blocks'][0]['_embedded']['viaplay:products']
        except:
            products = data['_embedded']['viaplay:blocks'][1]['_embedded']['viaplay:products']
    return products
    
def get_seasons(url):
    """Return all available seasons as a list."""
    data = make_request(url=url, method='get')
    seasons = []
    
    products = data['_embedded']['viaplay:blocks']
    for season in products:
        if season['type'] == 'season-list':
            seasons.append(season)
    return seasons
        
def list_seasons(url):
    seasons = get_seasons(url)
    listing = []
    for season in seasons:
        title = language(30014) + ' ' + season['title']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        parameters = {'action': 'listproducts', 'url': season['_links']['self']['href']}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.addSortMethod(_handle, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(_handle)
    
def item_information(item):
    """Return the product information in a xbmcgui.setInfo friendly tuple.
    Supported content types: episode, series, movie, sport"""
    type = item['type']
    mediatype = None
    title = None
    tvshowtitle = None
    season = None
    episode = None
    year = None
    plot = None
    director = None
    cast = []
    try:
        duration = int(item['content']['duration']['milliseconds']) / 1000
    except:
        duration = None
    try:
        imdb_code = item['content']['imdb']['id']
    except:
        imdb_code = None
    try:
        rating = float(item['content']['imdb']['rating'])
    except:
        rating = None
    try:
        votes = str(item['content']['imdb']['votes'])
    except:
        votes = None
    try:
        year = int(item['content']['production']['year'])
    except:
        year = None
    try:
        genres = []
        for genre in item['_links']['viaplay:genres']:
            genres.append(genre['title'])
        genre = ', '.join(genres)  
    except:
        genre = None
    try:
        mpaa = item['content']['parentalRating']
    except KeyError:
        mpaa = None
            
    if type == 'episode':
        mediatype = 'episode'
        title = item['content']['series']['episodeTitle'].encode('utf-8')
        tvshowtitle = item['content']['series']['title'].encode('utf-8')
        season = int(item['content']['series']['season']['seasonNumber'])
        episode = int(item['content']['series']['episodeNumber'])
        plot = item['content']['synopsis'].encode('utf-8')        
        xbmcplugin.setContent(_handle, 'episodes')
    elif type == 'series':
        mediatype = 'tvshow'
        title = item['content']['series']['title'].encode('utf-8')
        tvshowtitle = item['content']['series']['title'].encode('utf-8')
        try:
            plot = item['content']['series']['synopsis'].encode('utf-8')
        except KeyError:
            plot = item['content']['synopsis'].encode('utf-8') # needed for alphabetical listing
        xbmcplugin.setContent(_handle, 'tvshows')
    elif type == 'movie':
        mediatype = 'movie'
        title = item['content']['title'].encode('utf-8')
        plot = item['content']['synopsis'].encode('utf-8')
        try:
            for actor in item['content']['people']['actors']:
                cast.append(actor)
        except KeyError:
            pass
        try:
            directors = []
            for director in item['content']['people']['directors']:
                directors.append(director)
            director = ', '.join(directors)
        except KeyError:
            pass
        xbmcplugin.setContent(_handle, 'movies')
    elif type == 'sport':
        mediatype = 'video'
        title = item['content']['title'].encode('utf-8')
        plot = item['content']['synopsis'].encode('utf-8')
        xbmcplugin.setContent(_handle, 'movies')
    info = {
        'mediatype': mediatype,
        'title': title,
        'tvshowtitle': tvshowtitle,
        'season': season,
        'episode': episode,
        'year': year,
        'plot': plot,
        'duration': duration,
        'code': imdb_code,
        'rating': rating,
        'votes': votes,
        'genre': genre,
        'director': director,
        'mpaa': mpaa,
        'cast': cast
        }
    return info
        
def art(item):
    """Return the available art in a xbmcgui.setArt friendly tuple."""
    type = item['type']
    thumbnail = item['content']['images']['boxart']['url'].split('.jpg')[0] + '.jpg'
    fanart = item['content']['images']['hero169']['template'].split('.jpg')[0] + '.jpg'
    try:
        cover = item['content']['images']['coverart23']['template'].split('.jpg')[0] + '.jpg'
    except:
        cover = None
    banner = item['content']['images']['landscape']['url'].split('.jpg')[0] + '.jpg'    
    art = {
        'thumb': thumbnail,
        'fanart': fanart,
        'banner': banner,
        'cover': cover
        }
    return art

def play_video(playid, streamtype):
    # Create a playable item with a path to play.
    if streamtype == 'url':
        data = make_request(playid, 'get')
        guid = get_products(data)['system']['guid']
    else:
        guid = playid
    stream = get_streams(guid)
    if stream is not False:
        play_item = xbmcgui.ListItem(path=stream)
        play_item.setProperty('IsPlayable', 'true')
        if subtitles:
            play_item.setSubtitles(get_subtitles(subdict[guid]))
        # Pass the item to the Kodi player.
        xbmcplugin.setResolvedUrl(_handle, True, listitem=play_item)
    
def get_subtitles(subdict):
    """Download the SAMI subtitles, decode the HTML entities and save to addon profile.
    Return a list of the path to the subtitles."""
    subtitle_paths = []
    for samiurl in subdict:
        req = requests.get(samiurl)
        sami = req.content.decode('utf-8', 'ignore').strip()
        htmlparser = HTMLParser.HTMLParser()
        subtitle = htmlparser.unescape(sami).encode('utf-8')
        subtitle = subtitle.replace('  ', ' ') # replace two spaces with one
        
        if '_sv' in samiurl:
            path = os.path.join(addon_profile, 'swe.smi')
        elif '_no' in samiurl:
            path = os.path.join(addon_profile, 'nor.smi')
        elif '_da' in samiurl:
            path = os.path.join(addon_profile, 'dan.smi')
        elif '_fi' in samiurl:
            path = os.path.join(addon_profile, 'fin.smi')
        f = open(path, 'w')
        f.write(subtitle)
        f.close()
        subtitle_paths.append(path)
    return subtitle_paths
    
def sports_menu(url):
    # URL is hardcoded for now as the sports date listing is not available on all platforms
    if int(addon.getSetting('country')) > 2:
        live_url = 'https://content.viaplay.fi/androiddash-fi/urheilu2'
    else:
        live_url = 'http://content.viaplay.' + country + '/androiddash-' + country + '/sport2'
    listing = []
    categories = get_categories(live_url)
    now = datetime.now()
   
    for category in categories:
        date_object = datetime(*(time.strptime(category['date'], '%Y-%m-%d')[0:6])) # http://forum.kodi.tv/showthread.php?tid=112916
        title = category['date']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        if date_object.date() == now.date():
            parameters = {'action': 'sportstoday', 'url': category['href']}
        else:
            parameters = {'action': 'listsports', 'url': category['href']}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.endOfDirectory(_handle)
    
def sports_status(item):
    now = datetime.utcnow()
    producttime_start = dateutil.parser.parse(item['epg']['start'])
    producttime_start = producttime_start.replace(tzinfo=None)
    producttime_end = dateutil.parser.parse(item['epg']['end'])
    producttime_end = producttime_end.replace(tzinfo=None)
    if 'isLive' in item['system']['flags']:
        status = 'live'
    elif producttime_start > now:
        status = 'upcoming'
    elif producttime_end < now:
        status = 'archive'
    return status
    
def sports_today(url):
    types = ['live', 'upcoming', 'archive']
    listing = []
    for type in types:
        list_item = xbmcgui.ListItem(label=type.title())
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        parameters = {'action': 'listsportstoday', 'url': url, 'display': type}
        recursive_url = _url + '?' + urllib.urlencode(parameters)
        is_folder = True
        listing.append((recursive_url, list_item, is_folder))
    xbmcplugin.addDirectoryItems(_handle, listing, len(listing))
    xbmcplugin.endOfDirectory(_handle)
       
def router(paramstring):
    """Router function that calls other functions depending on the provided paramstring"""
    # Parse a URL-encoded paramstring to the dictionary of
    # {<parameter>: <value>} elements
    params = dict(urlparse.parse_qsl(paramstring))
    # Check the parameters passed to the plugin
    if params:
        if params['action'] == 'movie':
            movie_menu(params['url'])
        elif params['action'] == 'kids':
            kids_menu(params['url'])
        elif params['action'] == 'series':
            series_menu(params['url'])
        elif params['action'] == 'sport':
            sports_menu(params['url'])
        elif params['action'] == 'seasons':
            list_seasons(params['url'])
        elif params['action'] == 'nextpage':
            list_products(params['url'])
        elif params['action'] == 'listsports':
            list_products(params['url'])
        elif params['action'] == 'sportstoday':
            sports_today(params['url'])
        elif params['action'] == 'listsportstoday':
            list_products(params['url'], params['display'])
        elif params['action'] == 'play':
            play_video(params['playid'], params['streamtype'])
        elif params['action'] == 'sortby':
            sort_by(params['url'])
        elif params['action'] == 'listproducts':
            list_products(params['url'])
        elif params['action'] == 'listalphabetical':
            alphabetical_menu(params['url'])
    else:
        # If the plugin is called from Kodi UI without any parameters,
        # display the list of video categories
        root_menu(base_url)

if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    # We use string slicing to trim the leading '?' from the plugin call paramstring
    router(sys.argv[2][1:])
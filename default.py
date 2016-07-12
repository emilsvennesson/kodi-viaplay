# -*- coding: utf-8 -*-
"""
A Kodi plugin for Viaplay
"""
import sys
import os
import xbmc
import xbmcaddon
import xbmcvfs
import xbmcgui
import xbmcplugin
addon = xbmcaddon.Addon()
addon_path = xbmc.translatePath(addon.getAddonInfo('path'))
addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))
base_resource_path = os.path.join(addon_path, 'resources', 'lib')
sys.path.append(base_resource_path)
import cookielib
import urllib
import urlparse
import json
import requests
import uuid
from collections import defaultdict
from pycaption import SAMIReader, SRTWriter

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
base_url = 'http://content.viaplay.se/pc-se'
subdict = defaultdict(list)

if addon.getSetting('debug') == 'false':
    debug = False
else:
    debug = True

def addon_log(string):
    if debug:
        xbmc.log("%s: %s" %(logging_prefix, string))
                     
def make_request(url, method, payload=None, headers=None):
    """Make an HTTP request. Return the response as JSON."""
    addon_log('Request URL: %s' % url)
    addon_log('Headers: %s' % headers)
    if method == 'get':
        req = http_session.get(url, params=payload, headers=headers, allow_redirects=False, verify=False)
    else:
        req = http_session.post(url, data=payload, headers=headers, allow_redirects=False, verify=False)
    addon_log('Response code: %s' % req.status_code)
    addon_log('Response: %s' % req.content)
    cookie_jar.save(ignore_discard=True, ignore_expires=False)
    return json.loads(req.content)
   
def login(username, password):
    """Login to Viaplay. Return True/False based on the result."""
    url = 'http://login.viaplay.se/api/login/v1'
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
    url = 'http://login.viaplay.se/api/persistentLogin/v1'
    payload = {
        'deviceKey': 'atv-se'
    }
    data = make_request(url=url, method='get', payload=payload)
    if data['success'] is False:
        return False
    else:
        return True 

def get_streams(guid):
    """Return the URL for a stream. Append all available SAMI subtitle URL:s in the dict subguid."""
    url = 'http://play.viaplay.se/api/stream/byguid'
    payload = {
    'deviceId': uuid.uuid4(),
    'deviceName': 'atv',
    'deviceType': 'atv',
    'userAgent': 'AppleTV/2.4',
    'deviceKey': 'atv-se',
    'guid': guid
    }

    headers = {'User-Agent': 'AppleTV/2.4'}
    data = make_request(url=url, method='get', payload=payload, headers=headers)
    m3u8_url = data['_links']['viaplay:playlist']['href']
    try:
        subtitles = data['_links']['viaplay:sami']
        for sub in subtitles:
            url = sub['href']
            subdict[guid].append(url)
    except:
        addon_log('No subtitles found for guid %s' % guid)
    return m3u8_url
    
def get_categories(url):
    url = url.replace('https', 'http')
    url = url.replace('{?dtg}', '')
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
        type = category['name']
        title = category['title']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        if type == 'series':
            parameters = {'action': 'series', 'url': category['href']}
        elif type == 'movie':
            parameters = {'action': 'movie', 'url': category['href']}
        elif type == 'sport':
            parameters = {'action': 'sport', 'url': category['href']}
        elif type == 'kids':
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
    
def get_sortings(url):
    url = url.replace('https', 'http')
    url = url.replace('{?dtg}', '')
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
        parameters = {'action': 'listproducts', 'url': sorting['href']}
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
    
def list_products(url):
    url = url.replace('https', 'http')
    url = url.replace('{?dtg}', '')
    data = make_request(url=url, method='get')
    products = get_products(data)
    listing = []
    sort = None
    list_next_page = next_page(data)
    
    for item in products:
        type = item['type']
        if type == 'episode':
            title = item['content']['series']['episodeTitle']
            url = '{0}?action=play&guid={1}'.format(_url, item['system']['guid'])
            is_folder = False
            is_playable = 'true'
        if type == 'sport':
            if 'isLive' in item['system']['flags']:
                title = 'Live: ' + item['content']['title'].encode('utf-8')
            else:
                title = item['content']['title'].encode('utf-8')
            url = '{0}?action=play&guid={1}'.format(_url, item['system']['guid'])
            is_folder = False
            is_playable = 'true'
        elif type == 'movie':
            title = item['content']['title'].encode('utf-8') + ' ' + '(' + str(item['content']['production']['year']) + ')'
            url = '{0}?action=play&guid={1}'.format(_url, item['system']['guid'])
            is_folder = False
            is_playable = 'true'
        elif type == 'series':
            title = item['content']['series']['title'].encode('utf-8')      
            self_url = item['_links']['viaplay:page']['href']
            url = '{0}?action=seasons&url={1}'.format(_url, self_url)
            is_folder = True
            is_playable = 'false'
            sort = True
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', is_playable)
        list_item.setInfo('video', item_information(item))
        list_item.setArt(art(item))
        listing.append((url, list_item, is_folder))
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
    else:
        try:
            products = data['_embedded']['viaplay:blocks'][0]['_embedded']['viaplay:products']
        except:
            products = data['_embedded']['viaplay:blocks'][1]['_embedded']['viaplay:products']
    return products
    
def get_seasons(url):
    """Return all available seasons as a list."""
    url = url.replace('https', 'http')
    url = url.replace('{?dtg}', '')
    data = make_request(url=url, method='get')
    seasons = []
    
    products = data['_embedded']['viaplay:blocks']
    for season in products:
        if season['type'] == 'season-list':
            seasons_info = {
            'title': 'Season' + ' ' + season['title'],
            'url': season['_links']['self']['href']
            }
            seasons.append(seasons_info)
    return seasons
        
def list_seasons(url):
    url = url.replace('https', 'http')
    seasons = get_seasons(url)
    listing = []
    for season in seasons:
        title = season['title']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        list_item.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        list_item.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
        parameters = {'action': 'series', 'url': season['url']}
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
    genre = None
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
        genre = item['_links']['viaplay:genres'][0]['title']
    except:
        genre = None
            
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
        plot = item['content']['series']['synopsis'].encode('utf-8')
        xbmcplugin.setContent(_handle, 'tvshows')
    elif type == 'movie':
        mediatype = 'movie'
        title = item['content']['title'].encode('utf-8')
        plot = item['content']['synopsis'].encode('utf-8')
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
        'genre': genre
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

def play_video(guid):
    # Create a playable item with a path to play.
    play_item = xbmcgui.ListItem(path=get_streams(guid))
    play_item.setProperty('IsPlayable', 'true')
    play_item.setSubtitles((get_subtitles(subdict[guid])))
    # Pass the item to the Kodi player.
    xbmcplugin.setResolvedUrl(_handle, True, listitem=play_item)
    
def get_subtitles(subdict):
    """Convert subtitle from SAMI to SRT and download to addon profile."""
    subtitles = []
    for samiurl in subdict:
        req = requests.get(samiurl)
        sami = req.content.decode('utf-8', 'ignore').strip()
        try:
            srt = SRTWriter().write(SAMIReader().read(sami)).encode('utf-8')
        except:
            srt = None
        if '_sv' in samiurl:
            path = os.path.join(addon_profile, 'swe.srt')
        elif '_no' in samiurl:
            path = os.path.join(addon_profile, 'nor.srt')
        elif '_da' in samiurl:
            path = os.path.join(addon_profile, 'dan.srt')
        elif '_fi' in samiurl:
            path = os.path.join(addon_profile, 'fin.srt')
        if srt is not None:
            f = open(path, 'w')
            f.write(srt)
            f.close()
            subtitles.append(path)
    return subtitles


def main():
    if validate_session() is False:
        if login(username, password) is False:
            dialog = xbmcgui.Dialog()
            dialog.ok(language(30005),
            language(30006))
            sys.exit(0)
    root_menu(base_url)
    
def sports_menu(url):
    live_url = 'http://content.viaplay.se/androiddash-se/sport2' # hardcoded as it's not available on all platforms
    listing = []
    categories = get_categories(live_url)
    for category in categories:
        title = category['date']
        list_item = xbmcgui.ListItem(label=title)
        list_item.setProperty('IsPlayable', 'false')
        parameters = {'action': 'listsports', 'url': category['href'].replace('{&dtg}', '')}
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
        if params['action'] == 'listcategories':
            list_categories(params['url'])
        elif params['action'] == 'movie':
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
        elif params['action'] == 'play':
            play_video(params['guid'])
        elif params['action'] == 'sortby':
            sort_by(params['url'])
        elif params['action'] == 'listproducts':
            list_products(params['url'])
    else:
        # If the plugin is called from Kodi UI without any parameters,
        # display the list of video categories
        main()

if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    # We use string slicing to trim the leading '?' from the plugin call paramstring
    router(sys.argv[2][1:])
    
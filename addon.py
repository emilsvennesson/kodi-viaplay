# -*- coding: utf-8 -*-
"""
A Kodi add-on for Viaplay
"""
import sys
import os
import urllib
import urlparse
from datetime import datetime

from resources.lib.kodihelper import KodiHelper

base_url = sys.argv[0]
handle = int(sys.argv[1])
helper = KodiHelper(base_url, handle)


def run():
    try:
        router(sys.argv[2][1:])  # trim the leading '?' from the plugin call paramstring
    except helper.vp.ViaplayError as error:
        try:
            if error.value == 'MissingSessionCookieError':
                if helper.authorize():
                    router(sys.argv[2][1:])
        except helper.vp.ViaplayError as error:
            helper.dialog('ok', helper.language(30005), error.value)


def root_page():
    pages = helper.vp.get_root_page()

    for page in pages:
        params = {
            'action': page['name'] if page.get('name') else page['id'],
            'url': page['href']
        }
        helper.add_item(page['title'], params)
    helper.eod()


def list_start_page(url):
    collections = helper.vp.get_collections(url)

    for i in collections:
        params = {
            'action': 'list_products',
            'url': i['_links']['self']['href']
        }
        helper.add_item(i['title'], params)
    helper.eod()


def list_products_alphabetical(url):
    """List all products in alphabetical order."""
    title = helper.language(30013)
    parameters = {
        'action': 'list_products',
        'url': url + '?sort=alphabetical'
    }

    helper.add_item(title, parameters)


def list_alphabetical_letters(url):
    letters = helper.vp.get_letters(url)

    for letter in letters:
        if letter == '0-9':
            query = '#'  # 0-9 needs to be sent as a number sign
        else:
            query = letter.lower()

        parameters = {
            'action': 'list_products',
            'url': url + '&letter=' + urllib.quote(query)
        }

        helper.add_item(letter, parameters)
    helper.eod()


def list_next_page(url):
    title = helper.language(30018)
    params = {
        'action': 'list_products',
        'url': url
    }
    helper.add_item(title, params)


def list_products(url, filter_event=False):
    if filter_event:
        filter_event = filter_event.split(', ')

    products_dict = helper.vp.get_products(url, filter_event=filter_event)

    for product in products_dict['products']:
        content = product['type']
        try:
            playid = product['system']['guid']
            streamtype = 'guid'
        except KeyError:
            """The guid is not always available from the category listing.
            Send the self URL and let play_video grab the guid from there instead
            as it always provides more detailed data about each product."""
            playid = product['_links']['self']['href']
            streamtype = 'url'

        parameters = {
            'action': 'play_video',
            'playid': playid.encode('utf-8'),
            'streamtype': streamtype,
            'content': content
        }

        if content == 'episode':
            title = product['content']['series']['episodeTitle']
            playable = True
            set_content = 'episodes'

        elif content == 'sport':
            now = datetime.now()
            date_today = now.date()
            product_name = unicode(product['content']['title'])

            if date_today == product['event_date'].date():
                start_time = '%s %s' % (helper.language(30027), product['event_date'].strftime('%H:%M'))
            else:
                start_time = product['event_date'].strftime('%Y-%m-%d %H:%M')

            title = '[B]%s:[/B] %s' % (coloring(start_time, product['event_status']), product_name)

            if product['event_status'] == 'upcoming':
                parameters = {
                    'action': 'dialog',
                    'dialog_type': 'ok',
                    'heading': helper.language(30017),
                    'message': '%s [B]%s[/B].' % (helper.language(30016), start_time)
                }
                playable = False
            else:
                playable = True

            set_content = 'movies'

        elif content == 'movie':
            movie_name = product['content']['title'].encode('utf-8')
            movie_year = str(product['content']['production']['year'])
            title = '%s (%s)' % (movie_name, movie_year)

            if product['system']['availability']['planInfo']['isRental']:
                title = title + ' *'  # mark rental products with an asterisk

            playable = True
            set_content = 'movies'

        elif content == 'series':
            title = product['content']['series']['title'].encode('utf-8')
            season_url = product['_links']['viaplay:page']['href']
            parameters = {
                'action': 'list_seasons',
                'url': season_url
            }
            playable = False
            set_content = 'tvshows'

        helper.add_item(title, parameters, playable=playable, content=set_content, info=return_info(product, content), art=return_art(product, content))
    if products_dict['next_page']:
        list_next_page(products_dict['next_page'])
    helper.eod()


def list_seasons(url):
    """List all series seasons."""
    seasons = helper.vp.get_seasons(url)
    if len(seasons) == 1:
        # list products if there's only one season
        season_url = seasons[0]['_links']['self']['href']
        list_products(season_url)
    else:
        for season in seasons:
            season_url = season['_links']['self']['href']
            title = '%s %s' % (helper.language(30014), season['title'])
            parameters = {
                'action': 'list_products',
                'url': season_url
            }

            helper.add_item(title, parameters)
        helper.eod()


def return_info(product, content):
    """Return the product information in a xbmcgui.setInfo friendly dict.
    Supported content types: episode, series, movie, sport"""
    cast = []
    mediatype = None
    title = None
    tvshowtitle = None
    season = None
    episode = None
    plot = None
    director = None
    try:
        duration = int(product['content']['duration']['milliseconds']) / 1000
    except KeyError:
        duration = None
    try:
        imdb_code = product['content']['imdb']['id']
    except KeyError:
        imdb_code = None
    try:
        rating = float(product['content']['imdb']['rating'])
    except KeyError:
        rating = None
    try:
        votes = str(product['content']['imdb']['votes'])
    except KeyError:
        votes = None
    try:
        year = int(product['content']['production']['year'])
    except KeyError:
        year = None
    try:
        genres = []
        for genre in product['_links']['viaplay:genres']:
            genres.append(genre['title'])
        genre = ', '.join(genres)
    except KeyError:
        genre = None
    try:
        mpaa = product['content']['parentalRating']
    except KeyError:
        mpaa = None

    if content == 'episode':
        mediatype = 'episode'
        title = product['content']['series']['episodeTitle'].encode('utf-8')
        tvshowtitle = product['content']['series']['title'].encode('utf-8')
        season = int(product['content']['series']['season']['seasonNumber'])
        episode = int(product['content']['series']['episodeNumber'])
        plot = product['content']['synopsis'].encode('utf-8')

    elif content == 'series':
        mediatype = 'tvshow'
        title = product['content']['series']['title'].encode('utf-8')
        tvshowtitle = product['content']['series']['title'].encode('utf-8')
        try:
            plot = product['content']['series']['synopsis'].encode('utf-8')
        except KeyError:
            plot = product['content']['synopsis'].encode('utf-8')  # needed for alphabetical listing

    elif content == 'movie':
        mediatype = 'movie'
        title = product['content']['title'].encode('utf-8')
        plot = product['content']['synopsis'].encode('utf-8')
        try:
            for actor in product['content']['people']['actors']:
                cast.append(actor)
        except KeyError:
            pass
        try:
            directors = []
            for director in product['content']['people']['directors']:
                directors.append(director)
            director = ', '.join(directors)
        except KeyError:
            pass

    elif content == 'sport':
        mediatype = 'video'
        title = product['content']['title'].encode('utf-8')
        plot = product['content']['synopsis'].encode('utf-8')

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


def return_art(product, content):
    """Return the available art in a xbmcgui.setArt friendly dict."""
    try:
        boxart = product['content']['images']['boxart']['url'].split('.jpg')[0] + '.jpg'
    except KeyError:
        boxart = None
    try:
        hero169 = product['content']['images']['hero169']['template'].split('.jpg')[0] + '.jpg'
    except KeyError:
        hero169 = None
    try:
        coverart23 = product['content']['images']['coverart23']['template'].split('.jpg')[0] + '.jpg'
    except KeyError:
        coverart23 = None
    try:
        coverart169 = product['content']['images']['coverart23']['template'].split('.jpg')[0] + '.jpg'
    except KeyError:
        coverart169 = None
    try:
        landscape = product['content']['images']['landscape']['url'].split('.jpg')[0] + '.jpg'
    except KeyError:
        landscape = None

    if content == 'episode' or content == 'sport':
        thumbnail = landscape
    else:
        thumbnail = boxart
    fanart = hero169
    banner = landscape
    cover = coverart23
    poster = boxart

    art = {
        'thumb': thumbnail,
        'fanart': fanart,
        'banner': banner,
        'cover': cover,
        'poster': poster
    }

    return art


def search(url):
    query = helper.get_user_input(helper.language(30015))
    if query:
        url = '%s?query=%s' % (url, urllib.quote(query))
        list_products(url)


def sports_menu(url):
    event_date = ['today', 'upcoming', 'archive']

    for date in event_date:
        if date == 'today':
            title = helper.language(30027)
        elif date == 'upcoming':
            title = helper.language(30028)
        else:
            title = helper.language(30029)
        if date == 'today':
            parameters = {
                'action': 'list_sports_today',
                'url': url
            }
        else:
            parameters = {
                'action': 'list_sports_dates',
                'url': url,
                'event_date': date
            }

        helper.add_item(title, parameters)
    helper.eod()


def list_sports_today(url):
    event_status = [helper.language(30037), helper.language(30031)]
    for status in event_status:
        if status == helper.language(30037):
            filter = 'live, upcoming'
        else:
            filter = 'archive'
        parameters = {
            'action': 'list_products_sports_today',
            'url': url,
            'filter_sports_event': filter
        }

        helper.add_item(status, parameters)
    helper.eod()


def list_sports_dates(url, event_date):
    dates = helper.vp.get_sports_dates(url, event_date)
    for date in dates:
        title = date['date']
        parameters = {
            'action': 'list_products',
            'url': date['href']
        }

        helper.add_item(title, parameters)
    helper.eod()


def coloring(text, meaning):
    """Return the text wrapped in appropriate color markup."""
    if meaning == 'live':
        color = 'FF03F12F'
    elif meaning == 'upcoming':
        color = 'FFF16C00'
    elif meaning == 'archive':
        color = 'FFFF0EE0'
    colored_text = '[COLOR=%s]%s[/COLOR]' % (color, text)
    return colored_text


def show_auth_error(error):
    if error == 'UserNotAuthorizedForContentError':
        message = helper.language(30020)
    elif error == 'PurchaseConfirmationRequiredError':
        message = helper.language(30021)
    elif error == 'UserNotAuthorizedRegionBlockedError':
        message = helper.language(30022)
    else:
        message = error

    helper.dialog(dialog_type='ok', heading=helper.language(30017), message=message)


def router(paramstring):
    """Router function that calls other functions depending on the provided paramstring."""
    params = dict(urlparse.parse_qsl(paramstring))
    if 'action' in params:
        if params['action'] == 'viaplay:root':
            list_start_page(params['url'])
        elif params['action'] == 'sports_menu':
            sports_menu(params['url'])
        elif params['action'] == 'list_seasons':
            list_seasons(params['url'])
        elif params['action'] == 'list_products':
            list_products(params['url'])
        elif params['action'] == 'list_sports_today':
            list_sports_today(params['url'])
        elif params['action'] == 'list_products_sports_today':
            list_products(params['url'], params['filter_sports_event'])
        elif params['action'] == 'play_video':
            helper.play_video(params['playid'], params['streamtype'], params['content'])
        elif params['action'] == 'list_alphabetical_letters':
            list_alphabetical_letters(params['url'])
        elif params['action'] == 'search':
            search(params['url'])
        elif params['action'] == 'list_sports_dates':
            list_sports_dates(params['url'], params['event_date'])
        elif params['action'] == 'dialog':
            helper.dialog(params['dialog_type'], params['heading'], params['message'])
    else:
        root_page()

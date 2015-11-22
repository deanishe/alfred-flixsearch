#!/usr/bin/python
# encoding: utf-8
#
# Copyright © 2015 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2015-09-17
#

"""flix.py [options] [command] [arg]

Search FlixSearch.io.

Show which Netflix content is available and where.

Usage:
    flix.py search <query>
    flix.py config [<query>]
    flix.py countries [<query>]
    flix.py activate <country>
    flix.py deactivate <country>
    flix.py -h|--help

Options:
    -h, --help  Show this message and exit.

"""

from __future__ import print_function, unicode_literals, absolute_import

import hashlib
import htmlentitydefs
import re
import subprocess
import sys
import time

from bs4 import BeautifulSoup as BS
from bs4 import Tag
from docopt import docopt
from workflow import Workflow, web

# USER_AGENT = ('Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 '
#               '(KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36')
USER_AGENT = ('Alfred-Flixsearch/{0} '
              '(https://github.com/deanishe/alfred-flixsearch)')

# Countries where Netflix is available (that Flixsearch.io knows about)
COUNTRIES = [
    'Argentina',
    'Australia',
    'Austria',
    'Belgium',
    'Brazil',
    'Canada',
    'Colombia',
    'Denmark',
    'Finland',
    'France',
    'Germany',
    'Ireland',
    'Luxembourg',
    'Mexico',
    'Netherlands',
    'New Zealand',
    'Norway',
    'Sweden',
    'Switzerland',
    'UK',
    'USA',
]

# FLAGS = dict([(c, 'icons/{0}.png'.format(c)) for c in COUNTRIES])
FLAGS_ACTIVE = dict([(c, 'icons/{0} Active.png'.format(c))
                     for c in COUNTRIES])
FLAGS_INACTIVE = dict([(c, 'icons/{0} Inactive.png'.format(c))
                       for c in COUNTRIES])

ICON_BACK = 'icons/Back.png'
ICON_COUNTRIES = 'icons/Countries.png'
# ICON_FLAG = 'icons/EU.png'
ICON_HELP = 'icons/Help.png'
ICON_OFF = 'icons/Toggle Off.png'
ICON_ON = 'icons/Toggle On.png'
ICON_RESET = 'icons/Reset.png'
ICON_UPDATE_AVAILABLE = 'icons/Update Available.png'
ICON_UPDATE_NONE = 'icons/Update None.png'
ICON_WARNING = 'icons/Warning.png'

HELP_URL = 'https://github.com/deanishe/alfred-flixsearch#flixsearch-for-alfred'
DEFAULT_SETTINGS = {
    # Activate no countries by default
    'countries': []
}
UPDATE_SETTINGS = {
    'github_slug': 'deanishe/alfred-flixsearch'
}

log = None


def unescape(text):
    """Replace HTML entities with Unicode characters.

    From: http://effbot.org/zone/re-sub.htm#unescape-html
    """

    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text  # leave as is

    return re.sub("&#?\w+;", fixup, text)


def title_from_url(url):
    """Guess show/movie title based on URL.

    Args:
        url (str): Flixsearch.io URL

    Returns:
        str: Title (or `None`)
    """
    s = url.split('/')[-1]
    s = s.replace('-', ' ').title()
    if re.match(r'.+\d\d\d\d', s):
        s = '{} ({})'.format(s[:-4].strip(), s[-4:])
    return s


def flatten(elem, recursive=False):
    """Return the string contents of partial BS elem tree.

    :param elem: BeautifulSoup ``Tag`` or ``NavigableString``
    :param recursive: Whether to flatten children or entire subtree
    :returns: Flattened Unicode text contained in subtree

    """

    content = []

    if recursive:
        elems = elem.descendants
    else:
        elems = elem.contents

    for e in elems:
        # If processing recursively, a NavigableString for the
        # tag text will also be encountered
        if isinstance(e, Tag) and recursive:
            continue
        if hasattr(e, 'string') and e.string is not None:
            # log.debug('[%s] : %s', e.__class__.__name__, e.string)
            content.append(e.string)

    return unescape(re.sub(r'\s+', ' ', ''.join(content))).strip()


def retrieve_flixsearch_url(query):
    """Get HTML response from flixsearch.io.

    Returns Unicode HTML.

    """

    start = time.time()
    url = 'https://flixsearch.io/search/{0}'.format(query.encode('utf-8'))
    user_agent = USER_AGENT.format(wf.version)
    log.debug('Retrieving URL `%s` ...', url)
    headers = {'User-Agent': user_agent}

    r = web.get(url, headers=headers)

    r.raise_for_status()

    html = r.content
    # log.debug('HTML : %s', html)
    duration = time.time() - start
    log.debug('URL retrieved in %0.3f seconds', duration)

    return html


def parse_flixsearch_html(html):
    """Parse HTML and return search results."""

    start = time.time()
    results = []

    soup = BS(html, b'html5lib')
    elems = soup.find_all('div', 'card')
    log.debug('%d `card` elems found', len(elems))

    for i, elem in enumerate(elems):
        image = title = description = url = None
        countries = []
        genres = []

        # ---------------------------------------------------------
        # Parse subelements
        img_box = elem.find('div', 'card-image')
        if not img_box:
            log.error('No image box found : %r', elem)
            continue

        # flixsearch.io URL
        url = img_box.find('a').get('href')
        if not url:
            log.error('No URL found : %r', img_box)
            continue

        # tmbd.org image
        image = img_box.find('img').get('src')
        if not image:
            log.error('No image found : %r', img_box)
            continue
        else:
            image = image.decode('utf-8')

        # Film/show title
        title_elem = img_box.find('span', 'card-title')
        if title_elem:
            title = flatten(title_elem)
        else:
            # Try to extract from URL
            title = title_from_url(url)
            # log.error('No title found : %r', img_box)
            # continue

        # Genres & description
        content_box = elem.find('div', 'card-content')
        if not content_box:
            log.error('No content box found : %r', elem)
            continue

        paras = content_box.find_all('p')
        if len(paras) == 1:  # description only
            description = paras[0].string
        elif len(paras) == 2:  # expected results
            genres = [s.strip() for s in paras[0].string.split(',')]
            description = paras[1].string
        else:
            log.error('Found %d p elements, not 1 or 2 in %r',
                      len(paras), content_box)
            continue

        # genres = [s.strip() for s in paras[0].string.split(',')]
        # description = paras[1].string

        # Countries
        flag_box = elem.find('div', 'flags')
        if not flag_box:
            log.error('No flag box found : %r', elem)
            continue
        for e in flag_box.find_all('img', 'flag-post'):
            country = e.get('title')
            if country:
                countries.append(country)

        if not len(countries):
            log.error('No countries for %r', elem)
            continue

        if i == 0:
            log.debug('-' * 60)

        log.debug('Title       : %r', title)
        log.debug('URL         : %r', url)
        log.debug('Image       : %r', image)
        log.debug('Description : %r', description)
        log.debug('Genres      : %r', genres)
        log.debug('Countries   : %r', countries)
        log.debug('-' * 60)

        results.append(dict(title=title,
                            url=url,
                            image=image,
                            description=description,
                            genres=genres,
                            countries=countries))

    duration = time.time() - start
    log.debug('HTML parsed in %0.3f seconds', duration)

    return results


def flixsearch(query):
    """Retrieve results from flixsearch.io.

    Cache results for an hour.

    """

    def _wrapper():
        log.debug('New search for `%s`...', query)
        html = retrieve_flixsearch_url(query)
        results = parse_flixsearch_html(html)
        return results

    cache_key = 'results-' + hashlib.md5(query.encode('utf-8')).hexdigest()
    results = wf.cached_data(cache_key, _wrapper, max_age=3600)

    return results


class FlixSearch(object):
    """Workflow application."""

    def __init__(self):
        """Create new `FlixSearch` object."""

        self.wf = None

    def run(self, wf):
        """Run workflow. Call appropriate method based on CLI args."""

        self.wf = wf
        args = docopt(__doc__, argv=wf.args)
        # log.debug('args : %r', args)

        if args.get('search'):
            return self.do_search(args.get('<query>'))
        elif args.get('config'):
            return self.do_config(args.get('<query>'))
        elif args.get('countries'):
            return self.do_countries(args.get('<query>'))
        elif args.get('activate'):
            return self.do_activate(args.get('<country>'))
        elif args.get('deactivate'):
            return self.do_deactivate(args.get('<country>'))

    # ---------------------------------------------------------
    # Script actions

    def do_search(self, query):
        """Search flixsearch.io and display results in Alfred."""

        if not len(self.wf.settings.get('countries', [])):
            self.wf.add_item(
                'You must activate some countries before searching',
                'Enter "flixconf" to activate one or more countries',
                icon=ICON_WARNING)

            self.wf.send_feedback()
            return 0

        log.debug('Searching flixsearch.io for `%s` ...', query)
        results = flixsearch(query)
        log.debug('%d total results for `%s`', len(results), query)
        results = self._filter_for_countries(results)
        log.debug("%d results in user's countries for `%s`",
                  len(results), query)

        if not results:
            self.wf.add_item('No results for "{0}"'.format(query),
                             'Try a different query',
                             icon=ICON_WARNING)
            self.wf.send_feedback()
            return 0

        for r in results:
            subtitles = {
                'cmd': ', '.join(r['genres']),
                'alt': ', '.join(r['countries']),
                'ctrl': r['url'],
            }
            self.wf.add_item(r['title'],
                             # ', '.join(r['genres']),
                             r['description'],
                             modifier_subtitles=subtitles,
                             arg=r['url'],
                             valid=True,
                             uid=r['title'])

        self.wf.send_feedback()
        return 0

    def do_config(self, query):
        """Show configuration options."""

        # Call external trigger to re-run workflow
        if query == 'countries':
            return self._call_external_trigger('countries')

        # ---------------------------------------------------------
        # Update
        if self.wf.update_available:
            self.wf.add_item('A new version is available',
                             '↩ or ⇥ to update',
                             autocomplete='workflow:update',
                             icon=ICON_UPDATE_AVAILABLE)
        else:
            self.wf.add_item('Workflow is up to date',
                             icon=ICON_UPDATE_NONE)

        # ---------------------------------------------------------
        # Countries
        self.wf.add_item('Configure countries…',
                         '↩ or ⇥ to choose countries to search',
                         autocomplete='countries',
                         icon=ICON_COUNTRIES)

        # ---------------------------------------------------------
        # Workflow help
        self.wf.add_item('View help',
                         '↩ or ⇥ to open the help in your browser',
                         autocomplete='workflow:help',
                         icon=ICON_HELP)

        # ---------------------------------------------------------
        # Reset
        self.wf.add_item('Reset workflow',
                         '↩ or ⇥ to clear cache and settings',
                         autocomplete='workflow:reset',
                         icon=ICON_RESET)

        self.wf.send_feedback()
        return 0

    def do_countries(self, query):
        """Show list of available countries."""

        if query == 'config:goback':
            return self._call_external_trigger('config')

        user_countries = self.wf.settings.get('countries', [])

        all_selected = len(user_countries) == len(COUNTRIES)
        none_selected = len(user_countries) == 0

        # ---------------------------------------------------------
        # Show general country options
        if not query:
            self.wf.add_item('Back to config',
                             '↩ or ⇥ to go back',
                             autocomplete='config:goback',
                             icon=ICON_BACK)

            if not all_selected:
                self.wf.add_item('Activate all',
                                 '↩ to activate all countries',
                                 arg='activate ALL',
                                 valid=True,
                                 icon=ICON_ON)

            if not none_selected:
                self.wf.add_item('Deactivate all',
                                 '↩ to deactivate all countries',
                                 arg='deactivate ALL',
                                 valid=True,
                                 icon=ICON_OFF)

        # ---------------------------------------------------------
        # Show available/filtered countries
        countries = COUNTRIES[:]

        # Filter countries on query
        if query:
            countries = self.wf.filter(query, countries, min_score=30)

        if query and not countries:
            self.wf.add_item('No matching countries',
                             'Try a different query',
                             icon=ICON_WARNING)

        for c in countries:
            if c in user_countries:
                icon = FLAGS_ACTIVE[c]
                cmd = 'deactivate'
            else:
                icon = FLAGS_INACTIVE[c]
                cmd = 'activate'

            self.wf.add_item(c,
                             '↩ to {0} this country'.format(cmd),
                             arg='{0} "{1}"'.format(cmd, c),
                             valid=True,
                             icon=icon)

        self.wf.send_feedback()

    def do_deactivate(self, country):
        """Deactivate country and re-open settings."""

        return self._set_country_status(country, False)

    def do_activate(self, country):
        """Activate country and re-open settings."""

        return self._set_country_status(country, True)

    # ---------------------------------------------------------
    # Helpers

    def _set_country_status(self, country, activate=True):
        """Activate/deactivate country and post notification."""

        if 'countries' not in self.wf.settings:
            self.wf.settings['countries'] = []

        action = ('Deactivated', 'Activated')[activate]
        msg = '{0} {1}'.format(action, country)
        user_countries = self.wf.settings.get('countries', [])
        updated = False

        if country == 'ALL':
            if activate:
                self.wf.settings['countries'] = COUNTRIES[:]
                msg = 'Activated all countries'
                updated = True

            else:
                self.wf.settings['countries'] = []
                msg = 'Deactivated all countries'
                updated = True

        elif activate and country not in user_countries:
            self.wf.settings['countries'].append(country)
            updated = True

        elif not activate and country in user_countries:
            self.wf.settings['countries'].remove(country)
            updated = True

        if updated:
            self.wf.settings.save()
            log.debug(msg)
            print(msg)

        return self._call_external_trigger('countries')

    def _filter_for_countries(self, results):
        """Remove results that don't match user's configured countries."""

        filtered = []
        for r in results:
            item_countries = set(r['countries'])
            user_countries = set(self.wf.settings.get('countries', []))
            if item_countries & user_countries:
                filtered.append(r)

        return filtered

    def _call_external_trigger(self, trigger, argument=None):
        """Call Alfred external trigger with argument.

        Call external trigger via AppleScript.

        """

        script = ('tell application "Alfred 2" to run trigger "{0}" '
                  'in workflow '
                  '"net.deanishe.alfred-flixsearch"').format(trigger)

        if argument:
            script += ' with argument "{0}"'.format(argument)

        cmd = [b'/usr/bin/osascript', '-e', script.encode('utf-8')]
        retcode = subprocess.call(cmd)
        if retcode != 0:
            raise RuntimeError('Could not call Alfred via AppleScript')

        return 0


if __name__ == '__main__':
    wf = Workflow(
        default_settings=DEFAULT_SETTINGS,
        update_settings=UPDATE_SETTINGS,
        help_url=HELP_URL,
    )
    log = wf.logger
    app = FlixSearch()
    sys.exit(wf.run(app.run))

#!/usr/bin/env python
# encoding: utf-8
#
# Copyright © 2015 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2015-09-17
#

"""
Run a bunch of queries to try to determine which countries
Flixsearch.io knows about.
"""

from __future__ import print_function, unicode_literals, absolute_import

import logging
import os
from pprint import pprint
import sys

mydir = os.path.abspath(os.path.dirname(__file__))
wfdir = os.path.abspath(os.path.join(mydir, '../src'))

sys.path.insert(0, wfdir)

import flix
from flix import retrieve_flixsearch_url, parse_flixsearch_html

logging.basicConfig()
log = logging.getLogger('')
flix.log = log

# Use Netflix originals to (hopefully) capture the most countries
QUERIES = [
    'unbreakable kimmy schmidt',
    'orange is the new black',
    'house of cards',
    'sense8',
    'minimalitos',
]


def main():
    """Search Flixsearch.io for QUERIES."""

    countries = set()

    for q in QUERIES:
        html = retrieve_flixsearch_url(q)
        results = parse_flixsearch_html(html)
        for r in results:
            for c in r['countries']:
                countries.add(c)

    pprint(sorted(countries))


if __name__ == '__main__':
    main()

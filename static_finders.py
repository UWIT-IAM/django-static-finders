"""
A collection of django staticfiles finders to facilitate statics management.
"""
import os
from os.path import abspath
import requests
import shlex
import subprocess
import sys
from fnmatch import fnmatch
from itertools import chain
import logging
from importlib import import_module
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.contrib.staticfiles.finders import BaseFinder
from django.contrib.staticfiles.storage import FileSystemStorage
logger = logging.getLogger(__name__)
DEFAULT_CACHE = 'static-finders-cache'


class VendorFinder(BaseFinder):
    """
    VendorFinder will take a static name -> url dictionary and fetch the
    static from its source so it need not be duplicated in a repository.
    The map is a dictionary/generator pointed to by STATIC_FINDERS_VENDOR_MAP,
    and the files are cached in the STATIC_FINDERS_CACHE. The collectstatic
    command will locate the files from there.
    """
    def __init__(self):
        self.vendor_map = _get_vendor_map()
        if not self.vendor_map:
            err = 'missing required setting STATIC_FINDERS_VENDOR_MAP'
            raise ImproperlyConfigured(err)
        self.cache = getattr(settings, 'STATIC_FINDERS_CACHE', DEFAULT_CACHE)
        self.storage = FileSystemStorage(location=self.cache)

    def list(self, ignore_patterns):
        """List all files in vendor map, fetching them if necessary."""
        for path in self.vendor_map:
            self.find(path)
            yield path, self.storage

    def find(self, path, all=False):
        """
        Locate a file if it's in the vendor map. If it's not in the cache,
        fetch the static from its url.
        """
        path = path.replace('\\', '/')
        vendor_map = self.vendor_map
        if path not in vendor_map:
            return []

        cache_path = os.path.join(settings.BASE_DIR, self.cache, path)
        if not os.path.isfile(cache_path):
            url = vendor_map[path]
            _fetch_url(url, cache_path)
        return cache_path


class CompiledStaticsFinder(BaseFinder):
    """
    CompiledStaticsFinder will compile static files according to the
    configured STATIC_FINDERS_COMPILE_MAP, caching the results in
    STATIC_FINDERS_CACHE.
    """
    DEFAULT_IGNORE_PATTERNS = ['*.min.js']
    DEFAULT_COMPILE_MAP = {
        '*.js': 'npm run babel -- "{infile}" --out-file="{outfile}"'
    }
    SUPPORTED_FINDERS = [
        'django.contrib.staticfiles.finders.FileSystemFinder',
        'django.contrib.staticfiles.finders.AppDirectoriesFinder'
    ]

    def __init__(self, app_names=None, *args, **kwargs):
        self.cache = getattr(settings, 'STATIC_FINDERS_CACHE', DEFAULT_CACHE)
        self.storage = FileSystemStorage(location=self.cache)
        self.compile_map = getattr(settings, 'STATIC_FINDERS_COMPILE_MAP',
                                   self.DEFAULT_COMPILE_MAP)
        self.ignore_patterns = getattr(
            settings, 'STATIC_FINDERS_IGNORE_PATTERNS',
            self.DEFAULT_IGNORE_PATTERNS)
        self.finders = [_import_attribute(finder)()
                        for finder in settings.STATICFILES_FINDERS
                        if finder in self.SUPPORTED_FINDERS]

    def list(self, ignore_patterns):
        """
        List all of the compiled statics, compiling them if necessary.
        collectstatic will call this to generate its statics.
        """
        list_gens = (finder.list(ignore_patterns) for finder in self.finders)
        for path, storage in chain(*list_gens):
            if self.find(path, raise_errors=True):
                yield path, self.storage

    def find(self, path, all=False, raise_errors=False):
        """
        Find path according to our supported finders, and if it matches
        our compile_map, return a path to the compiled version.
        """
        found_paths = (finder.find(path, all=all) for finder in self.finders)
        source = next((f for f in found_paths if f), [])
        if not source:
            return source
        if any(fnmatch(path, pattern) for pattern in self.ignore_patterns):
            return []
        for pattern, command in self.compile_map.items():
            if fnmatch(path, pattern):
                break  # get the first matching command
        else:
            return []
        outfile = os.path.join(settings.BASE_DIR, self.cache, path)
        if _newest_file_index(outfile, source):
            kwargs = dict(infile=abspath(source), outfile=abspath(outfile))
            command = command.format(**kwargs)
            _makedirs(outfile)
            try:
                logger.info('running command {}'.format(command))
                _check_call(command)
            except (OSError, subprocess.CalledProcessError):
                logger.error('failed result for {}'.format(command))
                if raise_errors:
                    raise
                return []
        return outfile


def _fetch_url(url, destination_path):
    _makedirs(destination_path)
    response = requests.get(url)
    if response.status_code != 200:
        raise IOError('{} not found'.format(url))
    with open(destination_path, 'wb') as cache:
            cache.write(response.content)


def _makedirs(file_name):
    try:
        os.makedirs(os.path.dirname(file_name))
    except OSError:
        pass


def _import_attribute(path):
    module, attr = path.rsplit('.', 1)
    return getattr(import_module(module), attr)


def _get_vendor_map():
    """Load the vendor map from a dict or a string pointing to callable."""
    vendor_map = getattr(settings, 'STATIC_FINDERS_VENDOR_MAP', None)
    if isinstance(vendor_map, str):
        vendor_map = _import_attribute(vendor_map)
        if callable(vendor_map):
            vendor_map = vendor_map()
    return dict(vendor_map)


def _newest_file_index(*file_names):
    """Given file_names, return the index to the most recent one."""
    def getmtime(file_name):
        try:
            return os.path.getmtime(file_name)
        except OSError:
            return 0

    mtimes = map(getmtime, file_names)
    _, index = max((value, i) for i, value in enumerate(mtimes))
    return index


def _check_call(command):
    shell = False
    args = shlex.split(command)
    if sys.platform == 'win32':
        args = command
        shell = True
    return subprocess.check_call(args, shell=shell)

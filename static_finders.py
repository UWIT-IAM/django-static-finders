import os
from os.path import abspath
try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen
import shlex
import subprocess
from functools import partial
from fnmatch import fnmatch
import logging
from importlib import import_module
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.contrib.staticfiles.finders import BaseFinder, AppDirectoriesFinder
from django.contrib.staticfiles.storage import FileSystemStorage

logger = logging.getLogger(__name__)
DEFAULT_CACHE = 'static-finders-cache'
DEFAULT_NO_COMPILE_PATTERNS = ['*.min.js']
DEFAULT_COMPILE_MAP = {
    '*.js': 'npm run babel -- "{in_file}" --out-file="{out_file}"'
}


class VendorFinder(BaseFinder):
    def __init__(self):
        self.vendor_map = _get_vendor_map()
        if not self.vendor_map:
            raise ImproperlyConfigured(
                'missing required setting STATIC_FINDERS_VENDOR_MAP')
        self.cache = getattr(settings, 'STATIC_FINDERS_CACHE', DEFAULT_CACHE)
        self.storage = FileSystemStorage(location=self.cache)

    def list(self, ignore_patterns):
        for path in self.vendor_map:
            self.find(path)
            yield path, self.storage

    def find(self, path, all=False):
        path = path.replace('\\', '/')
        vendor_map = self.vendor_map
        if path not in vendor_map:
            return []

        cache_path = os.path.join(settings.BASE_DIR, self.cache, path)
        if not os.path.isfile(cache_path):
            _makedirs(cache_path)
            url = vendor_map[path]
            response = urlopen(url)
            if response.code != 200:
                raise IOError('{} not found'.format(url))
            with open(cache_path, 'wb') as cache:
                for chunk in iter(partial(response.read, 1024 * 64), b''):
                    cache.write(chunk)
        return cache_path


class CompiledStaticsFinder(AppDirectoriesFinder):
    def __init__(self, app_names=None, *args, **kwargs):
        super(self.__class__, self).__init__(app_names=app_names, *args,
                                             **kwargs)
        self.cache = getattr(settings, 'STATIC_FINDERS_CACHE', DEFAULT_CACHE)
        self.storage = FileSystemStorage(location=self.cache)
        self.compile_map = getattr(settings, 'STATIC_FINDERS_COMPILE_MAP',
                                   DEFAULT_COMPILE_MAP)
        self.no_compile_patterns = getattr(
            settings, 'STATIC_FINDERS_NO_COMPILE_PATTERNS',
            DEFAULT_NO_COMPILE_PATTERNS)

    def list(self, ignore_patterns):
        for path, storage in super(self.__class__, self).list(ignore_patterns):
            path_match = partial(fnmatch, path)
            if any(map(path_match, self.no_compile_patterns)):
                yield path, storage
            elif not any(map(path_match, self.compile_map)):
                yield path, storage
            else:
                self.find(path, raise_errors=True)  # trigger a compile
                yield path, self.storage

    def find(self, path, all=False, raise_errors=False):
        source = super(self.__class__, self).find(path, all=all)
        path_match = partial(fnmatch, path)
        if (source and not all and
                not any(map(path_match, self.no_compile_patterns)) and
                any(map(path_match, self.compile_map))):
            compile_command = next(
                command for pattern, command in self.compile_map.items()
                if path_match(pattern))
            out_file = os.path.join(settings.BASE_DIR, self.cache, path)
            if _newest_file_index(out_file, source):
                command = compile_command.format(in_file=abspath(source),
                                                 out_file=abspath(out_file))
                _makedirs(out_file)
                try:
                    logger.info('running command {}'.format(command))
                    subprocess.check_call(shlex.split(command))
                    source = out_file
                except (OSError, subprocess.CalledProcessError):
                    logger.error('failed result for {}'.format(command))
                    if raise_errors:
                        raise
            else:
                source = out_file
        return source


def _makedirs(file_name):
    try:
        os.makedirs(os.path.dirname(file_name))
    except OSError:
        pass


def _get_vendor_map():
    vendor_map = getattr(settings, 'STATIC_FINDERS_VENDOR_MAP', None)
    if isinstance(vendor_map, str):
        module, attr = vendor_map.rsplit('.', 1)
        vendor_map = getattr(import_module(module), attr)
        if callable(vendor_map):
            vendor_map = vendor_map()
    return vendor_map


def _newest_file_index(*file_names):
    def getmtime(file_name):
        try:
            return os.path.getmtime(file_name)
        except OSError:
            return 0

    mtimes = map(getmtime, file_names)
    _, index = max((value, i) for i, value in enumerate(mtimes))
    return index

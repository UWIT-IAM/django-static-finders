import os
import urllib2
import shlex
import subprocess
from functools import partial
from fnmatch import fnmatch
import logging
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.contrib.staticfiles.finders import BaseFinder, AppDirectoriesFinder
from django.contrib.staticfiles.storage import FileSystemStorage

logger = logging.getLogger(__name__)
DEFAULT_CACHE = 'static-finders-cache'
DEFAULT_NO_COMPILE_PATTERNS = ['*.min.js']
DEFAULT_COMPILE_MAP = {
    '*.js': 'babel {in_file} --presets=es2015 --out-file={out_file}'
}


class VendorFinder(BaseFinder):
    def __init__(self):
        if not hasattr(settings, 'STATIC_FINDERS_VENDOR_MAP'):
            raise ImproperlyConfigured(
                'missing required setting STATIC_FINDERS_VENDOR_MAP')
        self.storage = FileSystemStorage(location=_get_cache())

    def list(self, ignore_patterns):
        for path in settings.STATIC_FINDERS_VENDOR_MAP:
            self.find(path)
            yield path, self.storage

    def find(self, path, all=False):
        vendor_map = settings.STATIC_FINDERS_VENDOR_MAP
        if path not in vendor_map:
            return []

        cache_path = os.path.join(settings.BASE_DIR, _get_cache(), path)
        if not os.path.isfile(cache_path):
            _makedirs(cache_path)
            url = vendor_map[path]
            response = urllib2.urlopen(url)
            if response.code != 200:
                raise IOError('{} not found'.format(url))
            with open(cache_path, 'wb') as cache:
                for chunk in iter(partial(response.read, 1024 * 64), ''):
                    cache.write(chunk)
        return cache_path


class CompiledStaticsFinder(AppDirectoriesFinder):
    def __init__(self, app_names=None, *args, **kwargs):
        super(self.__class__, self).__init__(app_names=app_names, *args,
                                             **kwargs)
        self.storage = FileSystemStorage(location=_get_cache())

    def list(self, ignore_patterns):
        for path, storage in super(self.__class__, self).list(ignore_patterns):
            path_match = partial(fnmatch, path)
            compile_patterns = _get_compile_map().keys()
            if any(map(path_match, _get_no_compile_patterns())):
                yield path, storage
            elif not any(map(path_match, compile_patterns)):
                yield path, storage
            else:
                found_path = self.find(path)
                cache = _get_cache()
                if found_path and found_path.startswith(cache):
                    yield path, self.storage
                else:
                    yield path, storage

    def find(self, path, all=False):
        source = super(self.__class__, self).find(path, all=all)
        path_match = partial(fnmatch, path)
        compile_map = _get_compile_map()
        if (source and not all and
                not any(map(path_match, _get_no_compile_patterns())) and
                any(map(path_match, compile_map.keys()))):
            compile_command = next(
                command for pattern, command in compile_map.iteritems()
                if path_match(pattern))
            out_file = os.path.join(settings.BASE_DIR, _get_cache(), path)
            if _newest_file_index(out_file, source):
                command = compile_command.format(in_file=source,
                                                 out_file=out_file)
                try:
                    logger.info('running command {}'.format(command))
                    _makedirs(out_file)
                    subprocess.check_call(shlex.split(command))
                    source = out_file
                except subprocess.CalledProcessError:
                    logger.error('failed result for {}'.format(command))
        return source


def _makedirs(file_name):
    try:
        os.makedirs(os.path.dirname(file_name))
    except OSError:
        pass


def _get_cache():
    return getattr(settings, 'STATIC_FINDERS_CACHE', DEFAULT_CACHE)


def _get_compile_map():
    return getattr(settings, 'STATIC_FINDERS_COMPILE_MAP', DEFAULT_COMPILE_MAP)


def _get_no_compile_patterns():
    return getattr(settings, 'STATIC_FINDERS_NO_COMPILE_PATTERNS',
                   DEFAULT_NO_COMPILE_PATTERNS)


def _newest_file_index(*file_names):
    def getmtime(file_name):
        try:
            return os.path.getmtime(file_name)
        except OSError:
            return 0

    mtimes = map(getmtime, file_names)
    _, index = max((value, i) for i, value in enumerate(mtimes))
    return index
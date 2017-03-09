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


class VendorFinder(BaseFinder):
    def __init__(self):
        required_settings = ['STATIC_FINDERS_VENDOR_MAP',
                             'STATIC_FINDERS_CACHE']
        if not all(map(partial(hasattr, settings), required_settings)):
            raise ImproperlyConfigured('missing required settings')
        self.storage = FileSystemStorage(
            location=settings.STATIC_FINDERS_CACHE)

    def list(self, ignore_patterns):
        for path in settings.STATIC_FINDERS_VENDOR_MAP:
            self.find(path)
            yield path, self.storage

    def find(self, path, all=False):
        vendor_map = settings.STATIC_FINDERS_VENDOR_MAP
        if path not in vendor_map:
            return []

        cache_path = os.path.join(
            settings.BASE_DIR, settings.STATIC_FINDERS_CACHE, path)
        if not os.path.isfile(cache_path):
            if not os.path.isdir(os.path.dirname(cache_path)):
                os.makedirs(os.path.dirname(cache_path))
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
        super(self.__class__, self).__init__(app_names=app_names, *args, **kwargs)
        required_settings = ['STATIC_FINDERS_CACHE',
                             'STATIC_FINDERS_COMPILE_MAP']
        if not all(map(partial(hasattr, settings), required_settings)):
            raise ImproperlyConfigured('missing required settings')
        self.no_compile_patterns = getattr(
            settings, 'STATIC_FINDERS_NO_COMPILE_PATTERNS', [])
        self.storage = FileSystemStorage(
            location=settings.STATIC_FINDERS_CACHE)

    def list(self, ignore_patterns):
        for path, storage in super(self.__class__, self).list(ignore_patterns):
            path_match = partial(fnmatch, path)
            compile_patterns = settings.STATIC_FINDERS_COMPILE_MAP.keys()
            if any(map(path_match, self.no_compile_patterns)):
                yield path, storage
            elif not any(map(path_match, compile_patterns)):
                yield path, storage
            else:
                found_path = self.find(path)
                cache = settings.STATIC_FINDERS_CACHE
                if found_path and found_path.startswith(cache):
                    yield path, self.storage
                else:
                    yield path, storage

    def find(self, path, all=False):
        source = super(self.__class__, self).find(path, all=all)
        path_match = partial(fnmatch, path)
        compile_map = settings.STATIC_FINDERS_COMPILE_MAP
        if (source and not all and
                not any(map(path_match, self.no_compile_patterns)) and
                any(map(path_match, compile_map.keys()))):
            compile_command = next(
                command for pattern, command in compile_map.iteritems()
                if path_match(pattern))
            out_file = os.path.join(settings.BASE_DIR,
                                    settings.STATIC_FINDERS_CACHE,
                                    path)
            command = shlex.split(compile_command.format(in_file=source,
                                                         out_file=out_file))
            try:
                if not os.path.isdir(os.path.dirname(out_file)):
                    os.makedirs(os.path.dirname(out_file))
                subprocess.check_call(command)
                source = out_file
            except subprocess.CalledProcessError, IOError:
                logger.error('failed to call {}'.format(' '.join(command)))
        return source

import os
import shutil
from django.conf import settings
from static_finders import VendorFinder, CompiledStaticsFinder
from pytest import fixture
import logging


settings.configure()
logging.basicConfig()


@fixture
def settings(settings):
    settings.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    settings.STATIC_FINDERS_CACHE = 'pytest-static-cache'
    settings.STATIC_FINDERS_VENDOR_MAP = ('test_static_finders'
                                          '.get_fake_vendor_map')
    return settings


def test_vendor_finder_find(settings, static_cache):
    cache = settings.STATIC_FINDERS_CACHE
    expected_path = os.path.join(settings.BASE_DIR, cache, 'jquery.min.js')
    assert not os.path.isfile(expected_path)
    path = VendorFinder().find('jquery.min.js')
    assert path == expected_path
    assert os.path.isfile(expected_path)


def test_compiled_statics_finder_find(settings, static_cache, app_dir):
    path = CompiledStaticsFinder().find('foo.js')
    expected_path = os.path.join(static_cache, 'foo.js')
    assert path == expected_path
    with open(expected_path, 'rb') as out_file:
        out = out_file.read()
    assert out.startswith(b'"use strict";')


def test_compiled_statics_finder_list(settings, static_cache, app_dir):
    js, css = CompiledStaticsFinder().list([])
    assert css == ('blah.css', 'storage')
    js_file, js_storage = js
    assert js_file == 'foo.js'
    assert js_storage.location == static_cache
    assert os.path.isfile(os.path.join(static_cache, js_file))


def get_fake_vendor_map():
    return {'jquery.min.js': ('https://ajax.googleapis.com/ajax/libs'
                              '/jquery/1.11.3/jquery.min.js')}


@fixture
def static_cache(settings, request):
    cache_path = os.path.join(settings.BASE_DIR, settings.STATIC_FINDERS_CACHE)
    shutil.rmtree(cache_path, True)

    def fin():
        shutil.rmtree(cache_path, True)
    request.addfinalizer(fin)
    return cache_path


@fixture
def app_dir(settings, request, monkeypatch):
    app_dir = os.path.join(settings.BASE_DIR, 'fake_app')
    shutil.rmtree(app_dir, True)
    from django.contrib.staticfiles.finders import AppDirectoriesFinder

    def mock_find(self, name, all=None):
        if name in ('foo.js', 'blah.css'):
            return os.path.join(app_dir, name)
        else:
            return []

    def mock_list(self, ignore_patterns):
        yield 'foo.js', 'storage'
        yield 'blah.css', 'storage'
    monkeypatch.setattr(AppDirectoriesFinder, 'find', mock_find)
    monkeypatch.setattr(AppDirectoriesFinder, 'list', mock_list)
    os.mkdir(app_dir)
    with open(os.path.join(app_dir, 'foo.js'), 'wb') as js_file:
        js_file.write(b'var myString = `this is\na test`;')

    def fin():
        shutil.rmtree(app_dir, True)
    request.addfinalizer(fin)
    return app_dir

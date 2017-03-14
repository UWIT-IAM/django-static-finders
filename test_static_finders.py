import os
import shutil
from django.conf import settings
from static_finders import VendorFinder
from pytest import fixture


settings.configure()


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
    return static_cache

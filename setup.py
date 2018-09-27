from setuptools import setup


setup(name='django-static-finders',
      version='0.2',
      install_requires=['Django', 'requests'],
      py_modules=['static_finders'],
      setup_requires=['pytest-runner'],
      tests_require=['pytest', 'pytest-django', 'pytest-pep8', 'mock'])

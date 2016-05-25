
import logging

from requests import Session


logger = logging.getLogger('digger.Digger')


class Digger(object):
    REQUESTS_SUPPORTED_METHODS = ['get', 'options', 'head', 'post', 'put', 'patch', 'delete']

    def __init__(self, request_config=None, **kwargs):
        # Base config passed to any request
        self.request_config = request_config if request_config else {}
        # Any other config passed
        self.kwargs = kwargs
        # The requests session object
        self.session = Session()

    def request(self, method, url, **config):
        # Global request config
        combined_config = self.request_config.copy()
        # Updated with call specific request config
        combined_config.update(config)
        logger.info('{} : {}'.format(method, url))
        logger.debug(combined_config)
        # Call final wrapper of session request
        response = self.session_request(method, url, **combined_config)
        return response

    def session_request(self, method, url, **config):
        # Call the sessions "method" method so it can set some defaults before
        # the sessions "request" method is called
        if method.lower() in self.REQUESTS_SUPPORTED_METHODS:
            response = getattr(self.session, method.lower())(url, **config)
        # If the "method" isn't a supported method,
        # we call right through to the session's 'request' method
        else:
            response = self.session.request(method, url, **config)
        return response

    def __getattr__(self, name):
        # Map http methods to request, so we can do our work on the request
        if name in self.REQUESTS_SUPPORTED_METHODS:
            return lambda url, **kwargs: self.request(name, url, **kwargs)
        msg = "'{}' object has no attribute '{}'".format(self.__class__.__name__, name)
        logger.error(msg)
        raise AttributeError(msg)


from csv import DictWriter, writer
from datetime import datetime
from hashlib import md5
from json import loads
from os import getcwd
from os.path import abspath, join
from random import choice, randint
from sys import version_info
from time import time, sleep
from re import compile as re_compile
from logging import getLogger

from requests.exceptions import RequestException
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager

if version_info.major == 2:
    str_ = str

    def csv_open(path):
        return open(path, 'wb')
else:
    str_ = bytes
    basestring = (bytes, str)

    def csv_open(path):
        return open(path, 'wb', newline='')

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import netifaces
except ImportError:
    netifaces = None


logger = getLogger('digger.mixins')


__all__ = [
    'BaseUrlMixin',
    'BeautifulSoupMixin',
    'CsvMixin',
    'EnsureMixin',
    'JsonMixin',
    'MultipleIpAddressMixin',
    'PacingMixin',
    'RandomizeUserAgentMixin',
    'RegexMixin'
]


class BaseUrlMixin(object):
    def request(self, method, url, **config):
        if not url.startswith('https://') and \
                                    not url.startswith('http://') and self.kwargs.get('base_url'):
            base_url = self.kwargs['base_url']
            while base_url.endswith('/'):
                base_url = base_url[:-1]
            while url.startswith('/'):
                url = url[1:]
            url = '{}/{}'.format(base_url, url)
        return super(BaseUrlMixin, self).request(method, url, **config)


class BeautifulSoupMixin(object):
    def __init__(self, **kwargs):
        if BeautifulSoup is None:
            raise ImportError('No module named bs4')
        super(BeautifulSoupMixin, self).__init__(**kwargs)

    def bs_load(self, data, *args, **kwargs):
        data = data if isinstance(data, basestring) else data.text
        return BeautifulSoup(data, *args, **kwargs)

    def bs_get_form_fields(self, soup):
        '''
        Turn a BeautifulSoup form in to a dict of fields and default values
        Starting point from: https://gist.github.com/simonw/104413
        '''
        fields = {}
        for input_ in soup.find_all('input'):
            name = input_.get('name')
            value = input_.get('value')
            if name is None:
                continue
            elif input_.get('type') in ('checkbox', 'radio'):
                if input_.has_attr('checked') and value is None:
                    value = 'on'
            else:
                if name in fields:
                    value_so_far = fields[name]
                    if not isinstance(value_so_far, list):
                        value_so_far = [value_so_far]
                    value = value_so_far + [value]
            fields[name] = value
        for textarea in soup.find_all('textarea'):
            name = textarea.get('name')
            value = textarea.string or ''
            if name in fields:
                value_so_far = fields[name]
                if not isinstance(value_so_far, list):
                    value_so_far = [value_so_far]
                value = value_so_far + [value]
            fields[name] = value
        for select in soup.find_all('select'):
            value = ''
            options = select.find_all('option')
            is_multiple = select.has_attr('multiple')
            selected_options = [
                option for option in options
                if option.has_attr('selected')
            ]
            if not selected_options and options:
                selected_options = [options[0]]
            if not is_multiple:
                value = selected_options[0]['value']
            else:
                value = [option['value'] for option in selected_options]
            fields[select['name']] = value
        return fields


class CsvMixin(object):
    def __init__(self, csv_config=None, **kwargs):
        self.csv_config = csv_config if csv_config else {}

        self.csv_file_path = None
        self.csv_file_object = None
        self.csv_writer = None
        super(CsvMixin, self).__init__(**kwargs)

    def csv_get_headings(self):
        return self.kwargs.get('headings', [])

    def csv_get_row(self):
        return (
            dict(zip(self.csv_get_headings(), [''] * len(self.csv_get_headings())))
            if self.csv_get_headings()
            else []
        )

    def csv_open_file(self, path=None):
        self.csv_file_path = path if path is not None else self.kwargs.get(
            'output_path',
            join(
                self.kwargs.get('output_directory', abspath(getcwd())),
                self.kwargs.get(
                    'output_filename',
                    '{}_{}.csv'.format(
                        self.__class__.__name__, datetime.now().strftime(r'%Y-%m-%d-%H-%M')
                    )
                )
            )
        )
        self.csv_file_object = csv_open(self.csv_file_path)
        headings = self.csv_get_headings()
        if headings:
            self.csv_writer = DictWriter(
                self.csv_file_object, headings, **self.csv_config
            )
            self.csv_writer.writeheader()
        else:
            self.csv_writer = writer(self.csv_file_object, **self.csv_config)

    def csv_write_row(self, entry):
        def interator(e):
            if isinstance(e, dict):
                result = e.items()
            else:
                result = enumerate(e)
            return result

        for key, value in interator(entry):
            if isinstance(value, str_):
                value = value.decode('utf8')
            entry[key] = value
        self.csv_writer.writerow(entry)

    def csv_close_file(self):
        if self.csv_file_object:
            self.csv_file_object.close()
        self.csv_file_object = None
        self.csv_writer = None


class EnsureMixin(object):
    def session_request(self, method, url, **config):
        response = None
        for iteration in range(self.kwargs.get('ensure_attempts', 1)):
            try:
                response = super(EnsureMixin, self).session_request(method, url, **config)
            except KeyboardInterrupt:
                raise
            except RequestException:
                # Only raise if we made tried for the specified times
                if iteration == self.kwargs.get('ensure_attempts', 1):
                    raise
            if response is not None and response.ok:
                break
        return response


class JsonMixin(object):
    def json_loads(self, data, *args, **kwargs):
        data = data if isinstance(data, basestring) else data.text
        return loads(data, *args, **kwargs)


class MultipleIpAddressMixin(object):
    def __init__(self, multiple_ip_config=None, **kwargs):
        ip_addresses = multiple_ip_config.get('ip_addresses')
        randomize = multiple_ip_config.get('random', False)
        super(MultipleIpAddressMixin, self).__init__(**kwargs)
        self.multi_ip_register_adapter(ip_addresses, randomize)

    def multi_ip_register_adapter(self, ip_addresses=None, randomize=False):
        if ip_addresses is None:
            if netifaces is None:
                raise ImportError('No module named netifaces')
            ip_addresses = []
            for interface in netifaces.interfaces():
                if (
                        netifaces.ifaddresses(interface) and
                        netifaces.AF_INET in netifaces.ifaddresses(interface) and
                        netifaces.ifaddresses(interface)[netifaces.AF_INET] and
                        'addr' in netifaces.ifaddresses(interface)[netifaces.AF_INET][0] and
                        netifaces.ifaddresses(interface)[netifaces.AF_INET][0]['addr'] != '127.0.0.1'
                ):
                    ip_addresses.append(netifaces.ifaddresses(interface)[netifaces.AF_INET][0]['addr'])
        if ip_addresses:
            class SourceAddressAdapter(HTTPAdapter):
                # https://github.com/kennethreitz/requests/issues/2008#issuecomment-40793099
                def __init__(self, ip_addresses, randomize, **kwargs):
                    self.ip_index = 0
                    self.randomize = randomize
                    self.ip_addresses = ip_addresses
                    super(SourceAddressAdapter, self).__init__(**kwargs)

                def init_poolmanager(self, connections, maxsize, block=False):
                    if self.randomize:
                        ip_address = choice(self.ip_addresses)
                    else:
                        ip_address = self.ip_addresses[self.ip_index]
                        self.ip_index += 1
                        if self.ip_index == len(self.ip_addresses):
                            self.ip_index = 0
                    self.poolmanager = PoolManager(num_pools=connections,
                                                   maxsize=maxsize,
                                                   block=block,
                                                   source_address=(ip_address, 0))
            self.session.mount('http://', SourceAddressAdapter(ip_addresses, randomize))
            self.session.mount('https://', SourceAddressAdapter(ip_addresses, randomize))


class PacingMixin(object):
    def __init__(self, **kwargs):
        self.pacing_last_response_time = None
        super(PacingMixin, self).__init__(**kwargs)

    def session_request(self, method, url, **config):
        if 'pace' in self.kwargs and self.kwargs['pace'] > 0 and self.pacing_last_response_time:
            time_since = time() - self.pacing_last_response_time
            if time_since < self.kwargs['pace']:
                sleep(self.kwargs['pace'] - time_since)
        try:
            response = super(PacingMixin, self).session_request(method, url, **config)
        except RequestException:
            self.pacing_last_response_time = time()
            raise
        else:
            self.pacing_last_response_time = time()
        return response


class RandomizeUserAgentMixin(object):
    RANDOM_UA_USER_AGENT_TEMPLATE = (
        '{base}/{base_version} ({os} {os_version}) {md5_hash} {engine} {browser}/{browser_version}'
    )

    def request(self, method, url, **config):
        config.setdefault('headers', {})['User-Agent'] = self.random_ua_generate_user_agent()
        return super(RandomizeUserAgentMixin, self).request(method, url, **config)

    def random_ua_get_user_agent_template(self):
        return self.RANDOM_UA_USER_AGENT_TEMPLATE

    def random_ua_create_version(self, lengths, separator='.'):
        version_bits = []
        for length in lengths:
            value = str_(randint(pow(10, length - 1), pow(10, length) - 1))
            version_bits.append(value)
        return separator.join(version_bits)

    def random_ua_get_user_agent_values(self):
        os_options = ['Windows', 'Linux', 'OpenBSD', 'Mac OSX', 'Macintosh']
        options = {
            'Mozilla': ('Gecko', ['Internet Explorer', 'Firefox', 'Edge']),
            'Safari': ('WebKit', ['Chrome', 'Safari', 'Opera'])
        }
        base = choice(options.keys())

        return {
            'base': base,
            'base_version': self.random_ua_create_version([1, 1]),
            'os': choice(os_options),
            'os_version': self.random_ua_create_version([2, 2]),
            'browser': choice(options[base][1]),
            'browser_version': self.random_ua_create_version([3, 1, 2]),
            'engine': options[base][0],
            'engine_version': self.random_ua_create_version([2, 1, 3, 2]),
            'md5_hash': md5(str(time()).encode('utf8')).hexdigest(),
        }

    def random_ua_generate_user_agent(self):
        template = self.random_ua_get_user_agent_template()
        values = self.random_ua_get_user_agent_values()
        return template.format(**values)


class RegexMixin(object):
    def re_find(self, data, regex, start=0, end=None):
        data = data if isinstance(data, basestring) else data.text
        end = len(data) if end is None else end
        regex = re_compile(regex) if isinstance(regex, basestring) else regex
        return regex.search(data, start, end)

    def re_find_all(self, data, regex, start=0, end=None):
        matches = []
        match = self.re_find(data, regex, start, end)
        while match:
            matches.append(match)
            match = self.re_find(data, regex, match.end(), end)
        return matches

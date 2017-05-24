# -*- coding: utf-8 -*-
'''
Interface with a Junos device via proxy-minion. To connect to a junos device \
via junos proxy, specify the host information in the pillar in '/srv/pillar/details.sls'

.. code-block:: yaml

    proxy:
      proxytype: junos
      host: <ip or dns name of host>
      username: <username>
      port: 830
      password: <secret>

In '/srv/pillar/top.sls' map the device details with the proxy name.

.. code-block:: yaml

    base:
      'vmx':
        - details

After storing the device information in the pillar, configure the proxy \
in '/etc/salt/proxy'

.. code-block:: yaml

    master: <ip or hostname of salt-master>

Run the salt proxy via the following command:

.. code-block:: bash

    salt-proxy --proxyid=vmx


'''
from __future__ import absolute_import

# Import python libs
import logging
import subprocess
import socket
import pprint

# Import 3rd-party libs
try:
    HAS_JUNOS = True
    import jnpr.junos
    import jnpr.junos.utils
    import jnpr.junos.utils.config
    import jnpr.junos.utils.sw
except ImportError:
    HAS_JUNOS = False

__proxyenabled__ = ['junos']

thisproxy = {}

log = logging.getLogger(__name__)

# Define the module's virtual name
__virtualname__ = 'junos'


def __virtual__():
    '''
    Only return if all the modules are available
    '''
    if not HAS_JUNOS:
        return False, 'Missing dependency: The junos proxy minion requires the \'jnpr\' Python module.'

    return __virtualname__


def init(opts):
    '''
    Open the connection to the Junos device, login, and bind to the
    Resource class
    '''
    opts['multiprocessing'] = False
    log.debug('Opening connection to junos')

    if 'host' in opts['proxy'].keys():
        args = {"host": opts['proxy']['host']}
    else:
        args = {"host": None}

    if 'sock_fd' in opts.keys():
        args['sock_fd'] = opts['sock_fd']
    else:
        args['sock_fd'] = None

    optional_args = ['user',
                     'username',
                     'password',
                     'passwd',
                     'port',
                     'gather_facts',
                     'mode',
                     'baud',
                     'attempts',
                     'auto_probe',
                     'ssh_private_key_file',
                     'ssh_config',
                     'normalize'
                     ]

    if 'username' in opts['proxy'].keys():
        opts['proxy']['user'] = opts['proxy'].pop('username')
    proxy_keys = opts['proxy'].keys()
    for arg in optional_args:
        if arg in proxy_keys:
            args[arg] = opts['proxy'][arg]

    if args['sock_fd'] == None and args['host'] == None:
        log.debug('Listen for outbound-ssh Junos devices on port')
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', opts['proxy']['port']))
        s.listen(5)
        while True:
            client, addr = s.accept()
            _launch_junos_proxy(client, addr)

    else:
        thisproxy['conn'] = jnpr.junos.Device(**args)
        thisproxy['conn'].open()
        thisproxy['conn'].bind(cu=jnpr.junos.utils.config.Config)
        thisproxy['conn'].bind(sw=jnpr.junos.utils.sw.SW)
        thisproxy['initialized'] = True

def _launch_junos_proxy(client, addr):
    val = {
            'MSG-ID' : None,
            'MSG-VER' : None,
            'DEVICE-ID' : None
            }
    msg = ''
    count = 3
    while len(msg) < 100 and count > 0:
        c = client.recv(1)
        if c == '\r':
            continue

        if c == '\n':
            count = count - 1
            if msg.find(':'):
                (key, value) = msg.split(': ')
                val[key] = value
                msg = ''
        else:
            msg += c

    proxy_id = val['DEVICE-ID']
    fh = client.fileno()
    if val['DEVICE-ID']:
        log.debug('Launching salt-proxy for {0}'.format(val['DEVICE-ID']))
        proc = subprocess.Popen(['/usr/bin/salt-proxy',
            '--proxyid', val['DEVICE-ID'], '--sockfd', str(fh),
            '--disable-keepalive'])


def initialized():
    return thisproxy.get('initialized', False)


def conn():
    return thisproxy['conn']


def proxytype():
    '''
    Returns the name of this proxy
    '''
    return 'junos'


def get_serialized_facts():
    facts = dict(thisproxy['conn'].facts)
    if 'version_info' in facts:
        facts['version_info'] = \
            dict(facts['version_info'])
    # For backward compatibility. 'junos_info' is present
    # only of in newer versions of facts.
    if 'junos_info' in facts:
        for re in facts['junos_info']:
            facts['junos_info'][re]['object'] = \
                dict(facts['junos_info'][re]['object'])
    return facts


def ping():
    '''
    Ping?  Pong!
    '''
    return thisproxy['conn'].connected


def shutdown(opts):
    '''
    This is called when the proxy-minion is exiting to make sure the
    connection to the device is closed cleanly.
    '''
    log.debug('Proxy module {0} shutting down!!'.format(opts['id']))
    try:
        thisproxy['conn'].close()

    except Exception:
        pass

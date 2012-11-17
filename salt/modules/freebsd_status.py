'''
Module for returning various status data about a minion.
These data can be useful for compiling into stats later.
'''

import fnmatch
import os
import re

import struct
import salt.utils

__opts__ = {}


def __virtual__():
    '''
    Only run on FreeBSD systems
    '''
    return 'status' if __grains__['os'] == 'FreeBSD' else False


def _number(text):
    '''
    Convert a string to a number.
    Returns an integer if the string represents an integer, a floating
    point number if the string is a real number, or the string unchanged
    otherwise.
    '''
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def procs():
    '''
    Return the process data

    CLI Example::

        salt '*' status.procs
    '''
    # Get the user, pid and cmd
    ret = {}
    uind = 0
    pind = 0
    cind = 0
    plines = __salt__['cmd.run'](__grains__['ps']).split('\n')
    guide = plines.pop(0).split()
    if 'USER' in guide:
        uind = guide.index('USER')
    elif 'UID' in guide:
        uind = guide.index('UID')
    if 'PID' in guide:
        pind = guide.index('PID')
    if 'COMMAND' in guide:
        cind = guide.index('COMMAND')
    elif 'CMD' in guide:
        cind = guide.index('CMD')
    for line in plines:
        if not line:
            continue
        comps = line.split()
        ret[comps[pind]] = {'user': comps[uind],
                            'cmd': ' '.join(comps[cind:])}
    return ret


def custom():
    '''
    Return a custom composite of status data and info for this minon,
    based on the minion config file. An example config like might be::

        status.cpustats.custom: [ 'cpu', 'ctxt', 'btime', 'processes' ]

    Where status refers to status.py, cpustats is the function
    where we get our data, and custom is this function It is followed
    by a list of keys that we want returned.

    This function is meant to replace all_status(), which returns
    anything and everything, which we probably don't want.

    By default, nothing is returned. Warning: Depending on what you
    include, there can be a LOT here!

    CLI Example::

        salt '*' status.custom
    '''
    ret = {}
    for opt in __opts__:
        keys = opt.split('.')
        if keys[0] != 'status':
            continue
        func = '{0}()'.format(keys[1])
        vals = eval(func)

        for item in __opts__[opt]:
            ret[item] = vals[item]

    return ret


def uptime():
    '''
    Return the uptime for this minion

    CLI Example::

        salt '*' status.uptime
    '''
    return __salt__['cmd.run']('uptime').strip()


def loadavg():
    '''
    Return the load averages for this minion

    CLI Example::

        salt '*' status.loadavg
    '''
    load_avg = __salt__['sysctl.get']('vm.loadavg').replace(',', '.').split()
    return {'1-min':  _number(load_avg[1]),
            '5-min':  _number(load_avg[2]),
            '15-min': _number(load_avg[3])}

def _cputime(user, nice, system, irq, idle):
    return {'user': _number(user),
            'nice': _number(nice),
            'system': _number(system),
            'irq': _number(irq),
            'idle': _number(idle)
           }

def cpustats():
    '''
    Return the CPU stats for this minon

    CLI Example::

        salt '*' status.cpustats
    '''
    ret = {}
    cmd = '{0} -b kern.boottime'.format(salt.utils.which('sysctl'))
    ret['btime'] = struct.unpack('@i', __salt__['cmd.run'](cmd)[:4])[0]

    cpu = __salt__['sysctl.get']('kern.cp_time').split()
    ret['cpu'] = _cputime(*cpu)

    cpus = __salt__['sysctl.get']('kern.cp_times').split()
    for ncpu in range(len(cpus)/5):
        ret['cpu{0}'.format(ncpu)] = _cputime(*cpus[ncpu*5:(ncpu+1)*5])

    cmd = '{0} -i'.format(salt.utils.which('vmstat'))
    ret['intr'] = {}
    irqs = []
    for l in __salt__['cmd.run'](cmd).splitlines():
        if l.startswith('irq'):
            irqname, dev, total, rate = l.split()
            irqnum = _number(irqname.split(':')[0][3:])
            if len(irqs) < irqnum:
                irqs.extend((irqnum - len(irqs)) * [0])
            irqs[irqnum-1] = _number(total)
        elif l.startswith('Total'):
            ret['intr']['total'] = _number(l.split()[1])
    ret['intr']['irqs'] = irqs

    ret['processes'] = 0
    ret['procs_blocked'] = 0
    ret['procs_running'] = 0
    for l in __salt__['cmd.run'](__grains__['ps']).splitlines():
        pss = l.split()
        if pss[4] == '0': # kernel thread
            continue
        if 'D' in pss[7]:
            ret['procs_blocked'] += 1
        if 'R' in pss[7]:
            ret['procs_running'] += 1
        ret['processes'] += 1

    return ret


def _meminfo():
    '''
    Return the CPU stats for this minion

    CLI Example::

        salt '*' status.meminfo
    '''
    # TODO
    pass


def cpuinfo():
    '''
    Return the CPU info for this minion

    CLI Example::

        salt '*' status.cpuinfo
    '''
    if salt.utils.which('dmidecode'):
        return _cpuinfo_dmidecode()
    
    return ret


def diskstats():
    '''
    Return the disk stats for this minion

    CLI Example::

        salt '*' status.diskstats
    '''
    procf = '/proc/diskstats'
    if not os.path.isfile(procf):
        return {}
    stats = open(procf, 'r').read().split('\n')
    ret = {}
    for line in stats:
        if not line:
            continue
        comps = line.split()
        ret[comps[2]] = {'major': _number(comps[0]),
                         'minor': _number(comps[1]),
                         'device': _number(comps[2]),
                         'reads_issued': _number(comps[3]),
                         'reads_merged': _number(comps[4]),
                         'sectors_read': _number(comps[5]),
                         'ms_spent_reading': _number(comps[6]),
                         'writes_completed': _number(comps[7]),
                         'writes_merged': _number(comps[8]),
                         'sectors_written': _number(comps[9]),
                         'ms_spent_writing': _number(comps[10]),
                         'io_in_progress': _number(comps[11]),
                         'ms_spent_in_io': _number(comps[12]),
                         'weighted_ms_spent_in_io': _number(comps[13])}
    return ret


def diskusage(*args):
    '''
    Return the disk usage for this minion

    Usage::

        salt '*' status.diskusage [paths and/or filesystem types]

    CLI Example::

        salt '*' status.diskusage         # usage for all filesystems
        salt '*' status.diskusage / /tmp  # usage for / and /tmp
        salt '*' status.diskusage ext?    # usage for ext[234] filesystems
        salt '*' status.diskusage / ext?  # usage for / and all ext filesystems
    '''
    procf = '/proc/mounts'
    if not os.path.isfile(procf):
        return {}
    selected = set()
    fstypes = set()
    if not args:
        # select all filesystems
        fstypes.add('*')
    else:
        for arg in args:
            if arg.startswith('/'):
                # select path
                selected.add(arg)
            else:
                # select fstype
                fstypes.add(arg)

    if len(fstypes) > 0:
        # determine which mount points host the specified fstypes
        p = re.compile('|'.join(fnmatch.translate(fstype).format("(%s)")
                            for fstype in fstypes))
        with open(procf, 'r') as fp:
            for line in fp:
                comps = line.split()
                if len(comps) >= 3:
                    mntpt = comps[1]
                    fstype = comps[2]
                    if p.match(fstype):
                        selected.add(mntpt)

    # query the filesystems disk usage
    ret = {}
    for path in selected:
        fsstats = os.statvfs(path)
        blksz = fsstats.f_bsize
        available = fsstats.f_bavail * blksz
        total = fsstats.f_blocks * blksz
        ret[path] = {"available": available, "total": total}
    return ret


def vmstats():
    '''
    Return the virtual memory stats for this minion

    CLI Example::

        salt '*' status.vmstats
    '''
    procf = '/proc/vmstat'
    if not os.path.isfile(procf):
        return {}
    stats = open(procf, 'r').read().split('\n')
    ret = {}
    for line in stats:
        if not line:
            continue
        comps = line.split()
        ret[comps[0]] = _number(comps[1])
    return ret


def netstats():
    '''
    Return the network stats for this minion

    CLI Example::

        salt '*' status.netstats
    '''
    procf = '/proc/net/netstat'
    if not os.path.isfile(procf):
        return {}
    stats = open(procf, 'r').read().split('\n')
    ret = {}
    headers = ['']
    for line in stats:
        if not line:
            continue
        comps = line.split()
        if comps[0] == headers[0]:
            index = len(headers) - 1
            row = {}
            for field in range(index):
                if field < 1:
                    continue
                else:
                    row[headers[field]] = _number(comps[field])
            rowname = headers[0].replace(':', '')
            ret[rowname] = row
        else:
            headers = comps
    return ret


def netdev():
    '''
    Return the network device stats for this minion

    CLI Example::

        salt '*' status.netdev
    '''
    procf = '/proc/net/dev'
    if not os.path.isfile(procf):
        return {}
    stats = open(procf, 'r').read().split('\n')
    ret = {}
    for line in stats:
        if not line:
            continue
        if line.find(':') < 0:
            continue
        comps = line.split()
        # Fix lines like eth0:9999..'
        comps[0] = line.split(':')[0].strip()
        #Support lines both like eth0:999 and eth0: 9999
        comps.insert(1,line.split(':')[1].strip().split()[0])
        ret[comps[0]] = {'iface': comps[0],
                         'rx_bytes': _number(comps[1]),
                         'rx_compressed': _number(comps[7]),
                         'rx_drop': _number(comps[4]),
                         'rx_errs': _number(comps[3]),
                         'rx_fifo': _number(comps[5]),
                         'rx_frame': _number(comps[6]),
                         'rx_multicast': _number(comps[8]),
                         'rx_packets': _number(comps[2]),
                         'tx_bytes': _number(comps[9]),
                         'tx_carrier': _number(comps[15]),
                         'tx_colls': _number(comps[14]),
                         'tx_compressed': _number(comps[16]),
                         'tx_drop': _number(comps[12]),
                         'tx_errs': _number(comps[11]),
                         'tx_fifo': _number(comps[13]),
                         'tx_packets': _number(comps[10])}
    return ret


def w():
    '''
    Return a list of logged in users for this minion, using the w command

    CLI Example::

        salt '*' status.w
    '''
    user_list = []
    users = __salt__['cmd.run']('w -h').split('\n')
    for row in users:
        if not row:
            continue
        comps = row.split()
        rec = {'idle': comps[3],
               'jcpu': comps[4],
               'login': comps[2],
               'pcpu': comps[5],
               'tty': comps[1],
               'user': comps[0],
               'what': ' '.join(comps[6:])}
        user_list.append(rec)
    return user_list


def all_status():
    '''
    Return a composite of all status data and info for this minion.
    Warning: There is a LOT here!

    CLI Example::

        salt '*' status.all_status
    '''
    return {'cpuinfo': cpuinfo(),
            'cpustats': cpustats(),
            'diskstats': diskstats(),
            'loadavg': loadavg(),
            'meminfo': meminfo(),
            'netdev': netdev(),
            'netstats': netstats(),
            'uptime': uptime(),
            'vmstats': vmstats(),
            'w': w()}


def pid(sig):
    '''
    Return the PID or an empty string if the process is running or not.
    Pass a signature to use to find the process via ps.

    CLI Example::

        salt '*' status.pid <sig>
    '''
    cmd = "{0[ps]} | grep {1} | grep -v grep | awk '{{print $2}}'".format(
            __grains__, sig)
    return (__salt__['cmd.run_stdout'](cmd) or '').strip()



##########################################################################################
# tests/test_pdslogger.py
##########################################################################################

import pdslogger as P
from pdslogger import PdsLogger, LoggerError, STDOUT_HANDLER, NULL_HANDLER, file_handler
from filecache import FileCache, FCPath

from contextlib import redirect_stdout
import io
import logging
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
import warnings

TIMETAG = re.compile(r'\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d\.\d+')
ELAPSED = re.compile(r'0:00:00\.\d+')

LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
          'NORMAL', 'DS_STORE', 'DOT_', 'INVISIBLE']

def RESET():
    """Reset the logger database."""
    P._LOOKUP.clear()
    logging.Logger.manager.loggerDict.clear()
    P._DEFAULT_PARENT_NAME = 'pds'


class Test_PdsLogger(unittest.TestCase):

    def setUp(self):
        warnings.filterwarnings('ignore', message='.*unclosed file',
                                category=ResourceWarning)

    ######################################################################################
    # Constructors
    ######################################################################################

    def test_init(self):
        RESET()

        pl = PdsLogger('test')
        self.assertRaises(ValueError, PdsLogger, pl)

        logger = logging.getLogger('test2')
        pl = PdsLogger(logger)
        self.assertIs(pl._logger, logger)
        self.assertEqual(pl._logname, 'test2')

    def test_get_logger(self):
        RESET()
        pl = PdsLogger('test', limits={'debug': 0, 'eRRor': 22})
        pl2 = PdsLogger.get_logger('test')
        self.assertIs(pl, pl2)

        pl3 = PdsLogger.get_logger('test', limits={'debug': -1}, roots='dirpath/')
        self.assertIs(pl3, pl)
        self.assertEqual(pl._limits_by_name[0]['debug'], -1)
        self.assertEqual(pl._limits_by_name[0]['error'], 22)
        self.assertEqual(pl.roots, ['dirpath/'])

        pl4 = PdsLogger.getLogger('test')
        self.assertIs(pl4, pl)

        pl5 = PdsLogger.get_logger(pl4)
        self.assertIs(pl5, pl)

        pl6 = PdsLogger.get_logger(pl4._logger)
        self.assertIs(pl6, pl)

    def test_get_child(self):
        RESET()
        parent = PdsLogger.get_logger('test', levels={'bad': 40, 'very_bad': -50,
                                                                'so_so_bad': 60},
                                      limits={'bad': 7, 'debug': 0}, roots=['aa', 'bb'],
                                      level=99, timestamps=False, digits=7,
                                      lognames=False, pid=True, indent=False,
                                      levelnames=False, blanklines=False, colors=False,
                                      maxdepth=77)      # all non-default values
        parent.add_handler(STDOUT_HANDLER)

        son = parent.get_child('son')
        self.assertEqual(son.name, 'pds.test.son')
        self.assertEqual(son.parent.name, 'pds.test')
        self.assertEqual(son.handlers, [])
        self.assertEqual(son._level_by_name     , parent._level_by_name)
        self.assertEqual(son._level_names       , parent._level_names)
        self.assertEqual(son._level_name_aliases, parent._level_name_aliases)
        self.assertEqual(son._limits_by_name    , parent._limits_by_name)
        self.assertEqual(son.roots              , parent.roots)
        self.assertEqual(son.level      , parent.level)
        self.assertEqual(son._timestamps, parent._timestamps)
        self.assertEqual(son._digits    , parent._digits    )
        self.assertEqual(son._lognames  , parent._lognames  )
        self.assertEqual(son._pid       , parent._pid       )
        self.assertEqual(son._indent    , parent._indent    )
        self.assertEqual(son._levelnames, parent._levelnames)
        self.assertEqual(son._blanklines, parent._blanklines)
        self.assertEqual(son._colors    , parent._colors    )
        self.assertEqual(son._maxdepth  , parent._maxdepth  )

        daughter = parent.get_child('daughter', levels={'ok': 20}, limits={'ok': -1},
                                    roots=['cc'],
                                    level=88, timestamps=True, digits=8, lognames=True,
                                    pid=False, indent=True, levelnames=True,
                                    blanklines=True, colors=True, maxdepth=66)

        self.assertEqual(daughter.name, 'pds.test.daughter')
        self.assertEqual(daughter.parent.name, 'pds.test')
        self.assertEqual(daughter.handlers, [])

        del daughter._level_by_name['ok']       # force daughter to match parent on these
        del daughter._limits_by_name[0]['ok']
        daughter._roots.remove('cc/')

        self.assertEqual(daughter._level_by_name     , parent._level_by_name)
        self.assertEqual(daughter._level_names       , parent._level_names)
        self.assertEqual(daughter._level_name_aliases, parent._level_name_aliases)
        self.assertEqual(daughter._limits_by_name    , parent._limits_by_name)
        self.assertEqual(daughter.roots              , parent.roots)

        self.assertEqual(daughter.level      , 88   )
        self.assertEqual(daughter._timestamps, True )
        self.assertEqual(daughter._digits    , 8    )
        self.assertEqual(daughter._pid       , False)
        self.assertEqual(daughter._indent    , True )
        self.assertEqual(daughter._levelnames, True )
        self.assertEqual(daughter._blanklines, True )
        self.assertEqual(daughter._colors    , True )
        self.assertEqual(daughter._maxdepth  , 66   )

        adoptee = parent.getChild('adoptee')
        self.assertEqual(adoptee.name, 'pds.test.adoptee')
        self.assertEqual(adoptee.parent.name, 'pds.test')

        if sys.version_info >= (3, 12):
            self.assertEqual(parent.get_children(), {son, daughter, adoptee})
            self.assertEqual(parent.getChildren(), {son, daughter, adoptee})

    def test_as_pdslogger(self):
        RESET()
        logging.Logger.manager.loggerDict.clear()

        logger = logging.getLogger('abc')
        logger.addHandler(STDOUT_HANDLER)
        logger.addHandler(NULL_HANDLER)
        logger.setLevel(40)
        self.assertEqual(logger.parent.name, 'root')

        pl = PdsLogger.as_pdslogger(logger)
        self.assertEqual(pl.name, 'abc')
        self.assertEqual(pl.parent.name, 'root')
        self.assertEqual(pl.level, 40)
        self.assertEqual(pl.handlers, logger.handlers)
        self.assertEqual(pl._logname, 'abc')

        pl2 = PdsLogger.get_logger('abc', parent='')
        self.assertIs(pl, pl2)
        self.assertIs(pl._logger, pl2._logger)

        self.assertRaises(ValueError, PdsLogger, 'abc', parent='')

        pl3 = PdsLogger.as_pdslogger(pl2)
        self.assertIs(pl3, pl)

    def test_str(self):
        RESET()
        pl = PdsLogger('test', level=40)
        self.assertEqual(str(pl), '<PdsLogger pds.test (Level ERROR)>')

        pl = P.CriticalLogger()
        self.assertEqual(repr(pl), '<CriticalLogger pds.criticallog (Level CRITICAL)>')

        pl = P.CriticalLogger(levels={'very_bad': -P.CRITICAL})
        self.assertEqual(repr(pl), '<CriticalLogger pds.criticallog (Level VERY_BAD)>')

        pl = P.EasyLogger(level=41)
        self.assertEqual(str(pl), '<EasyLogger pds.easylog (Level 41)>')

    ######################################################################################
    # Formatting support
    ######################################################################################

    def test_set_format(self):
        RESET()
        pl = PdsLogger.get_logger('pds')

        # Check all defaults
        self.assertEqual(pl._logname, 'pds')
        self.assertEqual(pl.level, P.HIDDEN+1)
        self.assertEqual(pl._timestamps, True)
        self.assertEqual(pl._lognames, True)
        self.assertEqual(pl._pid, 0)
        self.assertEqual(pl._indent, True)
        self.assertEqual(pl._levelnames, True)
        self.assertEqual(pl._blanklines, True)
        self.assertEqual(pl._colors, True)
        self.assertEqual(pl._maxdepth, 6)

        pl.set_format(level=40)
        self.assertEqual(pl.level, 40)
        self.assertEqual(pl._timestamps, True)
        self.assertEqual(pl._lognames, True)
        self.assertEqual(pl._pid, 0)
        self.assertEqual(pl._indent, True)
        self.assertEqual(pl._levelnames, True)
        self.assertEqual(pl._blanklines, True)
        self.assertEqual(pl._colors, True)
        self.assertEqual(pl._maxdepth, 6)

        pl.set_format(timestamps=False, lognames=False, pid=True, indent=False,
                      levelnames=False, blanklines=False, colors=False, maxdepth=5)
        self.assertEqual(pl.level, 40)
        self.assertEqual(pl._timestamps, False)
        self.assertEqual(pl._lognames, False)
        self.assertNotEqual(pl._pid, 0)
        self.assertEqual(pl._indent, False)
        self.assertEqual(pl._levelnames, False)
        self.assertEqual(pl._blanklines, False)
        self.assertEqual(pl._colors, False)
        self.assertEqual(pl._maxdepth, 5)

    def test_pid(self):
        RESET()
        L = P.EasyLogger(pid=True)
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('PID')
        result = F.getvalue()
        match = re.fullmatch(r'.*easylog \| \d+ \|\| INFO \| PID', result[:-1])
        self.assertIsNotNone(match)

    def test_indent(self):
        RESET()
        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))
        result = result.replace('||', '|')

        L1 = P.EasyLogger(indent=False)
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level)

        result1 = F.getvalue()
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

    def test_max_depth(self):
        RESET()
        L = P.EasyLogger(maxdepth=4)
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('line 1')
            for t in range(4):
                L.open(f'tier {t}')
                L.debug(f'debug at tier {t}')
            self.assertRaises(ValueError, L.open, 'tier 5')

    ######################################################################################
    # Name and parent/child support
    ######################################################################################

    def test_parent(self):
        RESET()
        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))

        L1 = P.EasyLogger('foo.bar', parent='PDS')
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level)

        result1 = F.getvalue().replace('PDS.foo.bar', 'pds.easylog')
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

        L1 = P.EasyLogger('foo.bar', parent='foo')
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level)

        result1 = F.getvalue().replace('foo.bar', 'pds.easylog')
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

        L1 = P.EasyLogger('foo.bar', parent='')
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level)

        result1 = F.getvalue().replace('foo.bar', 'pds.easylog')
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

        l1 = PdsLogger('test')
        l2 = PdsLogger('test.abc')
        self.assertIs(l2.parent, l1)

        l1 = logging.getLogger('test2')
        l2 = logging.getLogger('test2.abc')
        pl1 = PdsLogger(l1)
        pl2 = PdsLogger(l2)
        self.assertIs(l2.parent, l1)
        self.assertIs(pl2.parent, pl1)

        p1 = PdsLogger.get_logger('abc')
        self.assertEqual(p1.name, 'pds.abc')

        pl = PdsLogger.get_logger('abc.def')
        self.assertEqual(pl.name, 'pds.abc.def')
        self.assertEqual(pl.parent.name, 'pds.abc')

        pl = PdsLogger.get_logger('bb.cc', parent='aa')
        self.assertEqual(pl.name, 'aa.bb.cc')
        self.assertEqual(pl.parent.name, 'root')
        pl2 = PdsLogger.get_logger('aa.bb', parent='')
        self.assertEqual(pl.parent.name, 'aa.bb')
        self.assertEqual(pl2.parent.name, 'root')
        _ = PdsLogger.get_logger('aa', parent='')
        self.assertEqual(pl2.parent.name, 'aa')

    def test_default_parent(self):
        RESET()

        self.assertEqual(P._DEFAULT_PARENT_NAME, 'pds')

        PdsLogger.set_default_parent('xxx.')
        self.assertEqual(P._DEFAULT_PARENT_NAME, 'xxx')

        PdsLogger.set_default_parent('aaa.bbb.ccc.')
        self.assertEqual(P._DEFAULT_PARENT_NAME, 'aaa.bbb.ccc')

        PdsLogger.set_default_parent('.')
        self.assertEqual(P._DEFAULT_PARENT_NAME, '')

        logger = logging.getLogger('test')
        PdsLogger.set_default_parent(logger)
        self.assertEqual(P._DEFAULT_PARENT_NAME, 'test')

        PdsLogger.set_default_parent('pds')
        logger = PdsLogger.get_logger('test')
        PdsLogger.set_default_parent(logger)
        self.assertEqual(P._DEFAULT_PARENT_NAME, 'pds.test')

    def test_full_logname(self):
        RESET()

        PdsLogger.set_default_parent('aa.bb.')
        self.assertEqual(PdsLogger._full_logname('cc'), 'aa.bb.cc')
        self.assertEqual(PdsLogger._full_logname('cc.dd'), 'aa.bb.cc.dd')
        self.assertEqual(PdsLogger._full_logname('aa'), 'aa')
        self.assertEqual(PdsLogger._full_logname('aa.ee'), 'aa.ee')
        self.assertEqual(PdsLogger._full_logname('bb'), 'aa.bb')
        self.assertEqual(PdsLogger._full_logname('bb.ee'), 'aa.bb.ee')

        PdsLogger.set_default_parent('')
        self.assertEqual(PdsLogger._full_logname('cc'), 'cc')
        self.assertEqual(PdsLogger._full_logname('cc.dd'), 'cc.dd')

        self.assertEqual(PdsLogger._full_logname('cc', 'aa.bb'), 'aa.bb.cc')
        self.assertEqual(PdsLogger._full_logname('cc.dd', 'aa.bb'), 'aa.bb.cc.dd')
        self.assertEqual(PdsLogger._full_logname('aa', 'aa.bb'), 'aa')
        self.assertEqual(PdsLogger._full_logname('aa.ee', 'aa.bb'), 'aa.ee')
        self.assertEqual(PdsLogger._full_logname('bb', 'aa.bb'), 'aa.bb')
        self.assertEqual(PdsLogger._full_logname('bb.ee', 'aa.bb'), 'aa.bb.ee')

        PdsLogger.set_default_parent('pds')

        self.assertEqual(PdsLogger._full_logname('xx', 'test'), 'test.xx')
        self.assertEqual(PdsLogger._full_logname('xx', logging.Logger('test')), 'test.xx')
        self.assertEqual(PdsLogger._full_logname('xx', PdsLogger('test')), 'pds.test.xx')

    ######################################################################################
    # Level support
    ######################################################################################

    def test_level(self):
        RESET()
        L = P.EasyLogger(level=1)
        F = io.StringIO()
        with redirect_stdout(F):
            L.hidden('HIDDEN')
        result = F.getvalue()
        self.assertTrue(result.endswith(' | pds.easylog || HIDDEN | HIDDEN\n'))

        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            L.hidden('HIDDEN')
        result = F.getvalue()
        self.assertEqual(result, '')

        L = P.EasyLogger(level='ERROR')
        LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL']
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)
        result = F.getvalue()
        result = result[:-1].split('\n')
        self.assertEqual(len(result), 2)

    def test_levels(self):
        RESET()
        L = P.EasyLogger(levels={'hidden': 44, 'foo': 20, 'bar': 33}, level=21)
        F = io.StringIO()
        with redirect_stdout(F):
            L.hidden('HIDDEN')
            L.log('FOO', 'FOO')
            L.log('foo', 'foo')
            L.log('BAR', 'BAR')
            L.log('bar', 'bar')
        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))  # eliminate time tags
        result = result[:-1].split('\n')
        self.assertEqual(result, [' | pds.easylog || HIDDEN | HIDDEN',
                                  ' | pds.easylog || BAR | BAR',
                                  ' | pds.easylog || BAR | bar'])

    def test_levelnames(self):
        RESET()
        pl = PdsLogger('test', levels={'VERY_BAD': -P.CRITICAL, 'WHATEVER': P.DEBUG,
                                       'HUH': P.WARNING+1},
                       timestamps=False, lognames=False, indent=False, blanklines=False)

        F = io.StringIO()
        with redirect_stdout(F):
            pl.log('whatever', 'Who knows?')
        result = F.getvalue()
        self.assertEqual(result, 'WHATEVER | Who knows?\n')

        F = io.StringIO()
        with redirect_stdout(F):
            pl.log('critical', 'CRITICAL')
        result = F.getvalue()
        self.assertEqual(result, 'VERY_BAD | CRITICAL\n')

        pl.set_level('huh')
        F = io.StringIO()
        with redirect_stdout(F):
            pl.warning('this will not print')
            pl.log('huh', 'This will print')
        result = F.getvalue()
        self.assertEqual(result, 'HUH | This will print\n')

        pl.set_level(P.HIDDEN + 1)
        F = io.StringIO()
        with redirect_stdout(F):
            pl.open('testing')
            pl.fatal('FATAL')
            pl.log('huH', 'HUH')
            pl.debug('DEBUG')
            pl.log('whatever', 'WHATEVER')
            pl.error('ERROR')
            pl.error('ANOTHER ERROR')
            pl.log('whatever', 'WHATEVER #2')
            pl.log('whatever', 'WHATEVER #3')
            pl.log(P.HIDDEN, 'HIDDEN')
            pl.close()
        result = F.getvalue()
        records = result.split('\n')
        self.assertEqual(records[-6], 'SUMMARY | 1 VERY_BAD message')
        self.assertEqual(records[-5], 'SUMMARY | 2 ERROR messages')
        self.assertEqual(records[-4], 'SUMMARY | 1 HUH message')
        self.assertEqual(records[-3], 'SUMMARY | 3 WHATEVER messages')
        self.assertEqual(records[-2], 'SUMMARY | 1 DEBUG message')

        ql = P.CriticalLogger()
        self.assertEqual(ql.level, P.CRITICAL)
        ql.setLevel(P.DEBUG)
        self.assertEqual(ql.level, P.CRITICAL)

    def test_merge_level_names(self):
        RESET()

        pl = P.EasyLogger(levels={'warn': -P.WARNING})
        self.assertEqual(pl._level_name_aliases,
                         {'fatal': 'critical', 'warning': 'warn'})
        self.assertEqual(pl._level_names[30], 'warn')

        pl = P.EasyLogger(levels={'oops': -P.FATAL})
        self.assertEqual(pl._level_name_aliases,
                         {'warn': 'warning', 'fatal': 'oops', 'critical': 'oops'})
        self.assertEqual(pl._level_names[50], 'oops')

        pl = P.EasyLogger(levels={'oops': P.FATAL})
        self.assertEqual(pl._level_name_aliases,
                         {'warn': 'warning', 'fatal': 'critical'})
        self.assertEqual(pl._level_names[50], 'critical')
        self.assertEqual(pl._level_by_name['oops'], 50)

        pl = P.EasyLogger(levels={'oops': -51})
        self.assertEqual(pl._level_name_aliases,
                         {'warn': 'warning', 'fatal': 'critical'})
        self.assertEqual(pl._level_names[51], 'oops')
        self.assertEqual(pl._level_by_name['oops'], 51)

    ######################################################################################
    # Limit support
    ######################################################################################

    def test_limits(self):
        RESET()
        L = P.EasyLogger(timestamps=False, lognames=False, blanklines=False,
                         indent=False, limits={'debug': 4})
        self.assertEqual(L.get_limit('debug'), 4)
        self.assertEqual(L.get_limit('error'), -1)
        limit_dict = L.get_limits().copy()
        limit_dict['debug'] = -1
        for name, limit in limit_dict.items():
            self.assertEqual(limit, -1, name)
        self.assertRaises(KeyError, L.get_limit, 'whatever')

        F = io.StringIO()
        with redirect_stdout(F):
            L.info('Begin')
            for t in range(1, 3):
                L.open(f'Tier {t}')
                for k in range(10):
                    L.debug(f'DEBUG {k+1} inside Tier {t}')
            L.info(f'INFO inside Tier {t}')
            for t in range(2, 0, -1):
                L.close()
                for k in range(10):
                    L.debug(f'DEBUG {k+1} after Tier {t}')
            L.info('End')
            L.close()
        result = F.getvalue()
        records = result.split('\n')
        self.assertEqual(records, ['INFO | Begin',
                                   'HEADER | Tier 1',
                                   'DEBUG | DEBUG 1 inside Tier 1',
                                   'DEBUG | DEBUG 2 inside Tier 1',
                                   'DEBUG | DEBUG 3 inside Tier 1',
                                   'DEBUG | DEBUG 4 inside Tier 1',
                                   'DEBUG | Additional DEBUG messages suppressed',
                                   'HEADER | Tier 2',
                                   'INFO | INFO inside Tier 2',
                                   'SUMMARY | Completed: Tier 2',
                                   'SUMMARY | 1 INFO message',
                                   'SUMMARY | 0 DEBUG messages reported of 10 total',
                                   'SUMMARY | Completed: Tier 1',
                                   'SUMMARY | 1 INFO message',
                                   'SUMMARY | 4 DEBUG messages reported of 30 total',
                                   'INFO | End',
                                   'SUMMARY | Completed: pds.easylog',
                                   'SUMMARY | 3 INFO messages',
                                   'SUMMARY | 4 DEBUG messages reported of 40 total',
                                   ''])

        L = P.EasyLogger(timestamps=False, lognames=False, blanklines=False,
                         indent=False)
        L.set_limit('debug', 4)
        F = io.StringIO()
        with redirect_stdout(F):
            L.open('Tier 1', limits={'debug': 12})
            for k in range(6):
                L.debug(f'DEBUG {k+1} inside Tier 1')
            L.close()
            for k in range(6):
                L.debug(f'DEBUG {k+1} inside Tier -')
            L.close()
        result = F.getvalue()
        records = result.split('\n')
        self.assertEqual(records, ['HEADER | Tier 1',
                                   'DEBUG | DEBUG 1 inside Tier 1',
                                   'DEBUG | DEBUG 2 inside Tier 1',
                                   'DEBUG | DEBUG 3 inside Tier 1',
                                   'DEBUG | DEBUG 4 inside Tier 1',
                                   'DEBUG | DEBUG 5 inside Tier 1',
                                   'DEBUG | DEBUG 6 inside Tier 1',
                                   'SUMMARY | Completed: Tier 1',
                                   'SUMMARY | 6 DEBUG messages',
                                   'DEBUG | Additional DEBUG messages suppressed',
                                   'SUMMARY | Completed: pds.easylog',
                                   'SUMMARY | 6 DEBUG messages reported of 12 total',
                                   ''])

        self.assertRaises(ValueError, P.EasyLogger, 'test', limits={'whatever': 3})

        L = P.EasyLogger(timestamps=False, lognames=False, blanklines=False,
                         indent=False, limits={'whatever': 1}, levels={'whatever': 40})
        F = io.StringIO()
        with redirect_stdout(F):
            L.log('whatever', 'WHATEVER')
            L.log('whatever', 'WHATEVER')
            L.log('whatever', 'WHATEVER')
        result = F.getvalue()
        records = result.split('\n')
        self.assertEqual(records[-2],
                         'WHATEVER | Additional WHATEVER messages suppressed')

    ######################################################################################
    # Root support
    ######################################################################################

    def test_roots(self):
        RESET()
        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('INFO', 'foo.bar')
            L.info('INFO', pathlib.Path('foo.bar'))
            L.info('INFO', 'a/long/prefix/before/foo.bar')
            L.info('INFO', pathlib.Path('a/long/prefix/before/foo.bar').as_posix())

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))
        parts = result.split('\n')
        self.assertEqual(parts[0], parts[1])
        self.assertEqual(parts[2], parts[3])
        self.assertTrue(parts[0].endswith('INFO: foo.bar'))
        self.assertTrue(parts[2].endswith('INFO: a/long/prefix/before/foo.bar'))

        L.add_root('a/')
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('INFO', 'foo.bar')
            L.info('INFO', pathlib.Path('foo.bar'))
            L.info('INFO', 'a/long/prefix/before/foo.bar')
            L.info('INFO', pathlib.Path('a/long/prefix/before/foo.bar').as_posix())

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))
        parts = result.split('\n')
        self.assertTrue(parts[2].endswith('INFO: long/prefix/before/foo.bar'))
        self.assertTrue(parts[3].endswith('INFO: long/prefix/before/foo.bar'))

        L.add_root('b', 'ccccccccccccccccc', 'a/long', 'b')
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('INFO', 'a/long/prefix/before/foo.bar')
            L.info('INFO', pathlib.Path('b/long/prefix/before/foo.bar').as_posix())

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))
        parts = result.split('\n')
        self.assertTrue(parts[0].endswith('INFO: prefix/before/foo.bar'))
        self.assertTrue(parts[1].endswith('INFO: long/prefix/before/foo.bar'))

        L = P.EasyLogger(roots='a/long')
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('INFO', 'a/long/prefix/before/foo.bar')
            L.info('INFO', pathlib.Path('a/long/prefix/before/foo.bar').as_posix())

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))
        parts = result.split('\n')
        self.assertTrue(parts[0].endswith('INFO: prefix/before/foo.bar'))
        self.assertTrue(parts[1].endswith('INFO: prefix/before/foo.bar'))

        L.replace_root('prefix', 'b')
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('INFO', 'a/long/prefix/before/foo.bar')
            L.info('INFO', pathlib.Path('a/long/prefix/before/foo.bar').as_posix())

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))
        parts = result.split('\n')
        self.assertTrue(parts[0].endswith('INFO: a/long/prefix/before/foo.bar'))
        self.assertTrue(parts[1].endswith('INFO: a/long/prefix/before/foo.bar'))

    ######################################################################################
    # Handler API
    ######################################################################################

    def test_add_handler(self):
        RESET()
        pl = PdsLogger.get_logger('abc.def')
        self.assertEqual(len(pl._handlers), 0)
        self.assertEqual(len(pl.handlers), 0)
        self.assertEqual(len(pl._logger.handlers), 0)

        pl.add_handler(STDOUT_HANDLER)
        self.assertIs(pl.handlers[0], STDOUT_HANDLER)
        self.assertIs(pl._handlers[0], STDOUT_HANDLER)
        self.assertEqual(len(pl.handlers), 1)

        pl.remove_handler(NULL_HANDLER)
        self.assertIs(pl.handlers[0], STDOUT_HANDLER)
        self.assertIs(pl._handlers[0], STDOUT_HANDLER)
        self.assertEqual(len(pl.handlers), 1)

        pl.add_handler(STDOUT_HANDLER)
        self.assertIs(pl.handlers[0], STDOUT_HANDLER)
        self.assertIs(pl._handlers[0], STDOUT_HANDLER)
        self.assertEqual(len(pl.handlers), 1)

        pl.add_handler(NULL_HANDLER)
        self.assertIs(pl.handlers[0], STDOUT_HANDLER)
        self.assertIs(pl._handlers[0], STDOUT_HANDLER)
        self.assertIs(pl.handlers[1], NULL_HANDLER)
        self.assertIs(pl._handlers[1], NULL_HANDLER)
        self.assertEqual(len(pl.handlers), 2)

        pl.remove_handler(P.stream_handler())           # a handler not in use
        self.assertIs(pl.handlers[0], STDOUT_HANDLER)
        self.assertIs(pl._handlers[0], STDOUT_HANDLER)
        self.assertIs(pl.handlers[1], NULL_HANDLER)
        self.assertIs(pl._handlers[1], NULL_HANDLER)
        self.assertEqual(len(pl.handlers), 2)

        pl.remove_handler(STDOUT_HANDLER)
        self.assertIs(pl.handlers[0], NULL_HANDLER)
        self.assertIs(pl._handlers[0], NULL_HANDLER)
        self.assertEqual(len(pl.handlers), 1)

        pl.remove_all_handlers()
        self.assertEqual(len(pl.handlers), 0)
        self.assertEqual(len(pl._handlers), 0)
        self.assertEqual(len(pl._logger.handlers), 0)

        pl.add_handler(STDOUT_HANDLER)
        pl.replace_handler(NULL_HANDLER)
        self.assertEqual(len(pl.handlers), 1)
        self.assertEqual(len(pl._handlers), 1)
        self.assertEqual(len(pl._logger.handlers), 1)
        self.assertIs(pl.handlers[0], NULL_HANDLER)

        with pl.open('title', handler=STDOUT_HANDLER):
            self.assertEqual(len(pl.handlers), 2)
            self.assertEqual(len(pl._handlers), 2)
            self.assertEqual(len(pl._logger.handlers), 2)
            self.assertIn(NULL_HANDLER, pl.handlers)
            self.assertIn(STDOUT_HANDLER, pl.handlers)

            self.assertEqual(pl._local_handlers[0], [NULL_HANDLER])
            self.assertEqual(pl._local_handlers[1], [STDOUT_HANDLER])

            pl.replace_handler(NULL_HANDLER)
            self.assertEqual(len(pl.handlers), 1)
            self.assertEqual(len(pl._handlers), 1)
            self.assertEqual(len(pl._logger.handlers), 1)
            self.assertEqual(pl._local_handlers[0], [NULL_HANDLER])
            self.assertEqual(pl._local_handlers[1], [])

            pl.add_handler(STDOUT_HANDLER)
            self.assertEqual(len(pl.handlers), 2)
            self.assertEqual(len(pl._handlers), 2)
            self.assertEqual(len(pl._logger.handlers), 2)
            self.assertEqual(pl._local_handlers[0], [NULL_HANDLER])
            self.assertEqual(pl._local_handlers[1], [STDOUT_HANDLER])

        self.assertEqual(len(pl.handlers), 1)
        self.assertEqual(len(pl._handlers), 1)
        self.assertEqual(len(pl._logger.handlers), 1)
        self.assertIs(pl.handlers[0], NULL_HANDLER)

        # Handlers on EasyLoggers
        L = P.EasyLogger()
        self.assertFalse(hasattr(L, '_warned_about_handlers'))
        self.assertFalse(L.has_handlers())
        self.assertFalse(L.hasHandlers())

        with warnings.catch_warnings(record=True) as w:     # empty list raises no warning
            L.add_handler()
        self.assertEqual(w, [])
        self.assertFalse(hasattr(L, '_warned_about_handlers'))

        with self.assertWarnsRegex(UserWarning,
                                   'class EasyLogger does not accept handlers'):
            L.add_handler(STDOUT_HANDLER)
        self.assertEqual(L._warned_about_handlers, True)
        self.assertFalse(L.has_handlers())

        with warnings.catch_warnings(record=True) as w:     # warn only once
            L.add_handler(NULL_HANDLER)
        self.assertEqual(w, [])
        self.assertFalse(L.has_handlers())

        L.remove_handler(STDOUT_HANDLER)
        self.assertFalse(L.has_handlers())

    ######################################################################################
    # More logger.Logging API
    ######################################################################################

    def test_api(self):
        RESET()

        logger = logging.getLogger('test')
        pl = PdsLogger.as_pdslogger(logger)
        pl.setLevel(30)
        el = P.EasyLogger(level=30)

        # propagate
        pl.propagate = True
        self.assertTrue(pl.propagate)
        self.assertTrue(logger.propagate)
        pl.propagate = False
        self.assertFalse(pl.propagate)
        self.assertFalse(logger.propagate)

        el.propagate = True
        self.assertFalse(el.propagate)
        el.propagate = False
        self.assertFalse(el.propagate)

        # disabled
        self.assertFalse(pl.disabled)
        self.assertFalse(el.disabled)

        # isEnabledFor
        self.assertTrue(pl.isEnabledFor(30))
        self.assertTrue(logger.isEnabledFor(30))
        self.assertFalse(pl.isEnabledFor(29))
        self.assertFalse(logger.isEnabledFor(29))

        self.assertTrue(el.isEnabledFor(30))
        self.assertFalse(el.isEnabledFor(29))

        # getEffectiveLevel
        self.assertEqual(pl.getEffectiveLevel(), 30)
        self.assertEqual(logger.getEffectiveLevel(), 30)
        self.assertEqual(el.getEffectiveLevel(), 30)

        pl.setLevel(20)
        el.setLevel(20)
        self.assertEqual(pl.getEffectiveLevel(), 20)
        self.assertEqual(logger.getEffectiveLevel(), 20)
        self.assertEqual(el.getEffectiveLevel(), 20)

    ######################################################################################
    # Open/close
    ######################################################################################

    def test_open_close(self):
        RESET()
        L = P.EasyLogger(timestamps=False, lognames=False)
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('Begin')
            for t in range(1, 4):
                L.open(f'Tier {t}')
                L.debug(f'DEBUG inside Tier {t}')
            L.info(f'INFO inside Tier {t}')
            for t in range(3, 0, -1):
                L.close()
                L.debug(f'DEBUG after Tier {t}')
            L.info('End')
            L.close()
        result = F.getvalue()
        records = result.split('\n')
        self.assertEqual(records, ['| INFO | Begin',
                                   '| HEADER | Tier 1',
                                   '-| DEBUG | DEBUG inside Tier 1',
                                   '-| HEADER | Tier 2',
                                   '--| DEBUG | DEBUG inside Tier 2',
                                   '--| HEADER | Tier 3',
                                   '---| DEBUG | DEBUG inside Tier 3',
                                   '---| INFO | INFO inside Tier 3',
                                   '--| SUMMARY | Completed: Tier 3',
                                   '--| SUMMARY | 1 INFO message',
                                   '--| SUMMARY | 1 DEBUG message',
                                   '',
                                   '--| DEBUG | DEBUG after Tier 3',
                                   '-| SUMMARY | Completed: Tier 2',
                                   '-| SUMMARY | 1 INFO message',
                                   '-| SUMMARY | 3 DEBUG messages',
                                   '',
                                   '-| DEBUG | DEBUG after Tier 2',
                                   '| SUMMARY | Completed: Tier 1',
                                   '| SUMMARY | 1 INFO message',
                                   '| SUMMARY | 5 DEBUG messages',
                                   '',
                                   '| DEBUG | DEBUG after Tier 1',
                                   '| INFO | End',
                                   '| SUMMARY | Completed: pds.easylog',
                                   '| SUMMARY | 3 INFO messages',
                                   '| SUMMARY | 6 DEBUG messages',
                                   '', ''])

        L = P.EasyLogger(timestamps=False, lognames=False, blanklines=False)
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('Begin')
            for t in range(1, 4):
                L.open(f'Tier {t}')
                L.debug(f'DEBUG inside Tier {t}')
            L.info(f'INFO inside Tier {t}')
            for t in range(3, 0, -1):
                L.close()
                L.debug(f'DEBUG after Tier {t}')
            L.info('End')
            L.close()
        result2 = F.getvalue()
        self.assertEqual(result2, result.replace('\n\n', '\n'))

        L = P.EasyLogger(timestamps=False, lognames=False, blanklines=False)
        F = io.StringIO()
        with redirect_stdout(F):
            for t in range(1, 4):
                L.open(f'Tier {t}', f'file{t}.dat')
            for t in range(3, 0, -1):
                L.close()
            L.close()
        result = F.getvalue()
        self.assertEqual(result, '| HEADER | Tier 1: file1.dat\n'
                                 '-| HEADER | Tier 2: file2.dat\n'
                                 '--| HEADER | Tier 3: file3.dat\n'
                                 '--| SUMMARY | Completed: Tier 3: file3.dat\n'
                                 '-| SUMMARY | Completed: Tier 2: file2.dat\n'
                                 '| SUMMARY | Completed: Tier 1: file1.dat\n'
                                 '| SUMMARY | Completed: pds.easylog\n')

        F = io.StringIO()
        with redirect_stdout(F):
            for t in range(1, 4):
                L.open(f'Tier {t}', f'file{t}.dat', level='critical')
            for t in range(3, 0, -1):
                L.close()
            L.close()
        result = F.getvalue()
        self.assertEqual(result, '| HEADER | Tier 1: file1.dat\n'
                                 '| SUMMARY | Completed: Tier 1: file1.dat\n'
                                 '| SUMMARY | Completed: pds.easylog\n')

        F = io.StringIO()
        with redirect_stdout(F):
            for t in range(1, 6):
                L.open(f'Tier {t}', level=10*t)
            for t in range(5, 0, -1):
                L.close()
            L.close()
        result = F.getvalue()
        self.assertEqual(result, '| HEADER | Tier 1\n'
                                 '-| HEADER | Tier 2\n'
                                 '--| HEADER | Tier 3\n'
                                 '--| SUMMARY | Completed: Tier 3\n'
                                 '-| SUMMARY | Completed: Tier 2\n'
                                 '| SUMMARY | Completed: Tier 1\n'
                                 '| SUMMARY | Completed: pds.easylog\n')

        L.set_level('error')
        for force in ('debug', 10, True):
            F = io.StringIO()
            with redirect_stdout(F):
                L.open('Tier 1', force=True)
                L.debug('DEBUG')
                self.assertEqual(L.message_count('debug'), 1)
                L.debug('DEBUG')
                L.close(force=force)
            result = F.getvalue()
            self.assertEqual(result, '| HEADER | Tier 1\n'
                                     '| SUMMARY | Completed: Tier 1\n'
                                     '| SUMMARY | 0 DEBUG messages reported of 2 total\n')

    ######################################################################################
    # Logging methods
    ######################################################################################

    def test_log_methods(self):
        RESET()
        L = P.EasyLogger()

        # Calls to individual logging methods
        F = io.StringIO()           # capture stdout to a string
        with redirect_stdout(F):
            L.debug('DEBUG')
            L.info('INFO')
            L.warn('WARNING')
            L.error('ERROR')
            L.fatal('CRITICAL')
            L.normal('NORMAL')
            L.ds_store('DS_STORE')
            L.dot_underscore('DOT_')
            L.invisible('INVISIBLE')
            L.blankline('info')
        result = F.getvalue()
        lines = result.split('\n')
        self.assertEqual(lines[-1], '')
        self.assertEqual(lines[-2], '')

        result = ''.join(TIMETAG.split(result))  # eliminate time tags

        lines = [line.split('|') for line in lines[:-2]]
        for k, line in enumerate(lines):
            self.assertEqual(line[1], ' pds.easylog ')
            self.assertEqual(line[2], '')
            self.assertEqual(line[3][1:-1], line[4][1:])
            self.assertEqual(line[3][1:-1], LEVELS[k])

        # Calls to log()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)
        result2 = F.getvalue()
        result2 = ''.join(TIMETAG.split(result2))
        self.assertEqual(result[:-1], result2)

        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level, suppress=True)
            L.blankline(force=True)
        result = F.getvalue()
        self.assertEqual(F.getvalue(), '\n')

        L.set_format(digits=0, levelnames=False, indent=False)
        F = io.StringIO()
        with redirect_stdout(F):
            L.error('oops')
        result = F.getvalue()
        self.assertRegex(result, r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d | pds.easylog | oops\n')

    def test_exception(self):
        RESET()
        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            try:
                _ = 1/0
            except ZeroDivisionError as e:
                L.exception(e, stacktrace=False)

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))
        self.assertEqual(result, ' | pds.easylog || EXCEPTION | '
                                 '**** ZeroDivisionError division by zero\n')

        F = io.StringIO()
        with redirect_stdout(F):
            try:
                _ = 1/0
            except ZeroDivisionError as e:
                L.exception(e, 'file.dat', stacktrace=False)

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))
        self.assertEqual(result, ' | pds.easylog || EXCEPTION | '
                                 '**** ZeroDivisionError division by zero: file.dat\n')

        F = io.StringIO()
        with redirect_stdout(F):
            try:
                _ = 1/0
            except ZeroDivisionError as e:
                L.exception(e, stacktrace=True)

        result = F.getvalue()
        self.assertRegex(result, '.*, in test_exception\n    _ = 1/0\n')

        F = io.StringIO()
        with redirect_stdout(F):
            try:
                _ = 1/0
            except ZeroDivisionError as e:
                L.exception(e, exc_info=True)

        result = F.getvalue()
        self.assertRegex(result, '.*, in test_exception\n    _ = 1/0\n')

        L = P.EasyLogger(timestamps=False, lognames=False)
        F = io.StringIO()
        with redirect_stdout(F):
            try:
                _ = 1/0
            except ZeroDivisionError:
                L.exception('EXCEPTION!', stacktrace=False, more='MORE')

        result = F.getvalue()
        self.assertEqual(result, '| EXCEPTION | EXCEPTION!\nMORE\n')

        # Using LoggerError
        F = io.StringIO()
        with redirect_stdout(F):
            try:
                try:
                    _ = 1/0
                except ZeroDivisionError as e:
                    raise LoggerError(e, filepath='a/b/c', level='error')

            except LoggerError as e:
                L.exception(e, stacktrace=False)

        result = F.getvalue()
        self.assertEqual(result, '| ERROR | ZeroDivisionError(division by zero): a/b/c\n')

        F = io.StringIO()
        with redirect_stdout(F):
            try:
                try:
                    _ = 1/0
                except ZeroDivisionError as e:
                    raise LoggerError(e, level=20, stacktrace=True) from e

            except LoggerError as e:
                L.exception(e, more='MORE!')

        result = F.getvalue()
        self.assertRegex(result, r'| INFO | ZeroDivisionError(division by zero)\n'
                                 r' *File ".*?", line \d+, in test_exception\n'
                                 r' *_ = 1/0\nMORE!\n')

        # From a logger
        logger = logging.getLogger('logger')
        L = PdsLogger.as_pdslogger(logger)
        dirpath = pathlib.Path(tempfile.mkdtemp()).resolve()
        handler = None
        try:
            logpath = dirpath / 'test.log'
            handler = P.file_handler(logpath, rotation='replace')
            L.add_handler(handler)
            try:
                _ = 1/0
            except ZeroDivisionError:
                L.exception('%(name)s--%(levelno)d--%(levelname)s',
                            stacktrace=False)

            content = logpath.read_text()
            self.assertEqual(content, 'logger--40--ERROR\n')

            try:
                _ = 1/0
            except ZeroDivisionError:
                L.exception('%(name)s--%(levelno)d--%(levelname)s',
                            exc_info=True, more='MORE', filepath='aa/bb')

            lskip = len(content)
            content = logpath.read_text()[lskip:]   # skip over previous content
            self.assertRegex(content, r'logger--40--ERROR: aa/bb\n'
                                      r'Traceback.*\n'
                                      r' *File ".*?", line \d+, in test_exception\n'
                                      r' *_ = 1/0\n'
                                      r'.*\n*'
                                      r'ZeroDivisionError: .*\n'
                                      r'MORE\n')
        finally:
            if handler:
                handler.close()  # Required for Windows to be able to delete the tree
            shutil.rmtree(dirpath)

    ######################################################################################
    # Message formatting utilities
    ######################################################################################

    def test_logged_filepath(self):
        RESET()

        pl = PdsLogger('test', roots='abc/')
        pl.add_root('def', 'ghi/jkl')

        self.assertEqual(pl._logged_filepath(''), '')
        self.assertEqual(pl._logged_filepath(pathlib.Path('')), '')
        self.assertEqual(pl._logged_filepath(FCPath('')), '')
        self.assertEqual(pl._logged_filepath('jkl'), 'jkl')
        self.assertEqual(pl._logged_filepath('ghi'), 'ghi')
        self.assertEqual(pl._logged_filepath('def/ghi'), 'ghi')
        self.assertEqual(pl._logged_filepath('abc/def'), 'def')
        self.assertEqual(pl._logged_filepath('ghi/jkl/mno'), 'mno')

        pl = PdsLogger('test2', roots=['abc', 'abcde'])
        self.assertEqual(pl._logged_filepath('abc/xyz'), 'xyz')
        self.assertEqual(pl._logged_filepath('abcde/xyz'), 'xyz')
        self.assertEqual(pl._logged_filepath('abc'), 'abc')
        self.assertEqual(pl._logged_filepath('abcd'), 'abcd')
        self.assertEqual(pl._logged_filepath('abcde'), 'abcde')
        self.assertEqual(pl._logged_filepath('abc/ff'), 'ff')
        self.assertEqual(pl._logged_filepath('abcd/ff'), 'abcd/ff')
        self.assertEqual(pl._logged_filepath('abcde/ff'), 'ff')

        pl = PdsLogger('test3', roots=['abcde', 'abc'])
        self.assertEqual(pl._logged_filepath('abc/xyz'), 'xyz')
        self.assertEqual(pl._logged_filepath('abcde/xyz'), 'xyz')

    def test_logged_level_name(self):
        RESET()
        L = P.EasyLogger()
        self.assertEqual(L._logged_level_name('FATAL'), 'CRITICAL')
        self.assertEqual(L._logged_level_name(49), 'ERROR+9')
        self.assertEqual(L._logged_level_name(40), 'ERROR')
        self.assertEqual(L._logged_level_name(2), 'HIDDEN+1')

        F = io.StringIO()
        with redirect_stdout(F):
            L.log(40, '40')

        result = F.getvalue()
        self.assertTrue(result.endswith('ERROR | 40\n'))

        F = io.StringIO()
        with redirect_stdout(F):
            L.log(49, '49')

        result = F.getvalue()
        self.assertTrue(result.endswith('ERROR+9 | 49\n'))

    def test_format_message(self):
        RESET()

        pl = P.EasyLogger()
        plfm = pl._format_message
        self.assertEqual(plfm(10, 'message'), 'message')
        self.assertEqual(plfm(10, '99.44%% pure'), '99.44% pure')
        self.assertEqual(plfm(10, '%.2f%% pure', 99.44), '99.44% pure')
        self.assertEqual(plfm(10, '%(percent).2f%% pure', percent=99.44), '99.44% pure')
        self.assertFalse(hasattr(pl, '_logrecords'))

        self.assertEqual(plfm(10, '%(name)s--%(levelno)d--%(levelname)s'),
                         'pds.easylog--10--DEBUG')
        self.assertEqual(plfm(20, '%(name)s--%(levelno)d--%(levelname)s'),
                         'pds.easylog--20--INFO')
        self.assertTrue(hasattr(pl, '_logrecords'))

        self.assertRegex(plfm(30, '%(created)s|%(relativeCreated)s||%(msecs)d'),
                         r'\d+\.\d+|\d+\.\d+|\d+$')
        self.assertRegex(plfm(30, '%(filename)s|%(pathname)s'),
                         r'__init__\.py|.*/rms-pdslogger/pdslogger/__init__\.py$')
        self.assertRegex(plfm(30, '%(processName)s|%(process)d'),
                         r'MainProcess|\d+$')
        self.assertRegex(plfm(30, '%(module)s|%(lineno)d'),
                         r'__init__|\d+$')
        self.assertRegex(plfm(30, '%(asctime)s|%(extra_value)s', extra_value='EXTRA'),
                         r'\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d,\d\d\d|EXTRA$')
        if sys.version_info >= (3, 12):
            self.assertRegex(plfm(30, '%(taskName)s'), 'None$')

    ######################################################################################
    # Alternative loggers
    ######################################################################################

    def test_errorlogger(self):
        RESET()
        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result)).replace('easylog', 'errorlog')

        # force=True
        L1 = P.ErrorLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level, force=True)

        result1 = F.getvalue()
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

        # force=False
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level, force=False)

        result1 = F.getvalue()
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result1, " | pds.errorlog || ERROR | ERROR\n"
                                  " | pds.errorlog || CRITICAL | CRITICAL\n"
                                  " | pds.errorlog || DOT_ | DOT_\n")

    def test_criticallogger(self):
        RESET()
        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result)).replace('easylog', 'criticallog')

        # force=True
        L1 = P.CriticalLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level, force=True)

        result1 = F.getvalue()
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

        # force=False
        F = io.StringIO()
        with redirect_stdout(F):
            L1.critical('FATAL')
            for level in LEVELS:
                L1.log(level, level, force=False)

        result1 = F.getvalue()
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result1, " | pds.criticallog || CRITICAL | FATAL\n"
                                  " | pds.criticallog || CRITICAL | CRITICAL\n")

    def test_nulllogger(self):
        RESET()
        L = P.NullLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)
                L.log(level, level, force=True)
        self.assertEqual(F.getvalue(), '')

    ######################################################################################
    # LoggerError
    ######################################################################################

    def test_loggererror(self):
        RESET()
        err = LoggerError('message')
        self.assertEqual(str(err), 'message')
        err.level = 30
        err.force = False
        err.stacktrace = False

        err2 = LoggerError(err)
        self.assertEqual(str(err2), 'message')
        err2.level = 30
        err2.force = False
        err2.stacktrace = False

        err = LoggerError('message', 'filepath', level='debug', force=True)
        self.assertEqual(str(err), 'message: filepath')
        err.level = 10
        err.force = True
        err.stacktrace = False

        err2 = LoggerError(err)
        self.assertEqual(str(err2), 'message: filepath')
        err2.level = 10
        err2.force = True
        err2.stacktrace = False

        err1 = ValueError('this is a ValueError')
        err = LoggerError(err1, level=25)
        self.assertEqual(str(err), 'ValueError(this is a ValueError)')
        err.level = 25
        err.force = False
        err.stacktrace = False

        err2 = LoggerError(err)
        self.assertEqual(str(err2), 'ValueError(this is a ValueError)')
        err2.level = 25
        err2.force = False
        err2.stacktrace = False

        err = LoggerError(err1, 'filepath', stacktrace=True)
        self.assertEqual(str(err), 'ValueError(this is a ValueError): filepath')
        err.level = 30
        err.force = False
        err.stacktrace = True

        err2 = LoggerError(err)
        self.assertEqual(str(err2), 'ValueError(this is a ValueError): filepath')
        err2.level = 30
        err2.force = False
        err2.stacktrace = True

    ######################################################################################
    # Handlers
    ######################################################################################

    def test_file_handlers(self):
        RESET()
        dirpath = pathlib.Path(tempfile.mkdtemp()).resolve()
        info = None
        warn = None
        error = None
        debug = None
        handler = None
        try:
            info = P.info_handler(dirpath)
            self.assertEqual(info.baseFilename, str(dirpath / 'INFO.log'))

            warn = P.warning_handler(dirpath, rotation='number')
            self.assertEqual(warn.baseFilename, str(dirpath / 'WARNINGS.log'))
            self.assertFalse((dirpath / 'WARNINGS_v001.log').exists())
            warn.close()

            # repeat to get _v1
            warn = P.warning_handler(dirpath, rotation='number')
            self.assertEqual(warn.baseFilename, str(dirpath / 'WARNINGS.log'))
            self.assertTrue((dirpath / 'WARNINGS_v001.log').exists())
            warn.close()

            # repeat to get _v2
            warn = P.warning_handler(dirpath, rotation='number')
            self.assertEqual(warn.baseFilename, str(dirpath / 'WARNINGS.log'))
            self.assertTrue((dirpath / 'WARNINGS_v002.log').exists())
            warn.close()

            (dirpath / 'WARNINGS_v100.log').touch()
            (dirpath / 'WARNINGS_vNNN.log').touch()
            warn = P.warning_handler(dirpath, rotation='number')
            self.assertEqual(warn.baseFilename, str(dirpath / 'WARNINGS.log'))
            self.assertTrue((dirpath / 'WARNINGS_v101.log').exists())

            error = P.error_handler(dirpath, rotation='ymd')
            pattern = dirpath.as_posix() + '/' + r'ERRORS_\d\d\d\d-\d\d-\d\d\.log'
            self.assertIsNotNone(re.fullmatch(pattern,
                                              error.baseFilename.replace('\\', '/')))

            debug = P.file_handler(dirpath / 'DEBUG.txt', rotation='ymdhms',
                                   level='DEBUG', suffix='_test')
            pattern = dirpath.as_posix() + '/' + \
                       r'DEBUG_\d\d\d\d-\d\d-\d\dT\d\d-\d\d-\d\d_test\.txt'
            self.assertIsNotNone(re.fullmatch(pattern,
                                              debug.baseFilename.replace('\\', '/')))

            L = P.PdsLogger('test')
            self.assertRaises(ValueError, P.PdsLogger, 'pds.test')  # duplicate name
            self.assertEqual(L.has_handlers(), False)
            self.assertEqual(L.hasHandlers(), False)
            self.assertEqual(len(L.handlers), 0)

            handlers = [debug, info, warn, error]
            sizes = [0, 0, 0, 0]

            def got_bigger():
                """1 where the filehandler has new content; 0 otherwise."""
                answers = []
                for k, handler in enumerate(handlers):
                    new_size = os.path.getsize(handler.baseFilename)
                    answers.append(int(new_size > sizes[k]))
                    sizes[k] = new_size
                return tuple(answers)

            L.add_handler(*handlers)
            self.assertEqual(L.has_handlers(), True)
            self.assertEqual(L.hasHandlers(), True)
            self.assertEqual(len(L.handlers), 4)

            F = io.StringIO()
            with redirect_stdout(F):
                L.debug('debug')
                self.assertEqual(got_bigger(), (1, 0, 0, 0))
                L.info('info')
                self.assertEqual(got_bigger(), (1, 1, 0, 0))
                L.warn('warn')
                self.assertEqual(got_bigger(), (1, 1, 1, 0))
                L.error('error')
                self.assertEqual(got_bigger(), (1, 1, 1, 1))
                L.fatal('fatal')
                self.assertEqual(got_bigger(), (1, 1, 1, 1))

                L.open('open')
                self.assertEqual(got_bigger(), (1, 1, 0, 0))
                L.close()
                self.assertEqual(got_bigger(), (1, 1, 0, 0))

                L.remove_handler(warn)
                L.debug('debug')
                self.assertEqual(got_bigger(), (1, 0, 0, 0))
                L.info('info')
                self.assertEqual(got_bigger(), (1, 1, 0, 0))
                L.warn('warn')
                self.assertEqual(got_bigger(), (1, 1, 0, 0))
                L.error('error')
                self.assertEqual(got_bigger(), (1, 1, 0, 1))

                L.open('open')
                L.add_handler(warn)
                self.assertEqual(got_bigger(), (1, 1, 0, 0))

                L.debug('debug')
                self.assertEqual(got_bigger(), (1, 0, 0, 0))
                L.info('info')
                self.assertEqual(got_bigger(), (1, 1, 0, 0))
                L.warn('warn')
                self.assertEqual(got_bigger(), (1, 1, 1, 0))
                L.error('error')
                self.assertEqual(got_bigger(), (1, 1, 1, 1))
                L.close()

                L.warn('warn')
                self.assertEqual(got_bigger(), (1, 1, 0, 0))

            result = F.getvalue()
            self.assertEqual(result, '')

            L.remove_all_handlers()
            F = io.StringIO()
            with redirect_stdout(F):
                L.fatal('fatal')
                self.assertEqual(got_bigger(), (0, 0, 0, 0))
            result = F.getvalue()
            self.assertIn('CRITICAL', result)

            for handler in handlers:
                handler.close()

            # Handlers using paths
            L = P.PdsLogger('test2')
            file1 = dirpath / 'handler1.log'
            file2 = pathlib.Path(dirpath / 'handler2.log')
            file3 = FCPath(dirpath / 'handler3.log')
            L.add_handler(file1, file2, file3, NULL_HANDLER)
            self.assertEqual(len(L.handlers), 4)
            L.add_handler(NULL_HANDLER)
            self.assertEqual(len(L.handlers), 4)

            L.debug('DEBUG')

            self.assertTrue(os.path.exists(file1))
            self.assertTrue(file2.exists())
            self.assertTrue(file3.exists())

            with warnings.catch_warnings():     # ignore warning that the file is open
                warnings.filterwarnings('ignore', category=ResourceWarning)
                L.add_handler(str(file3))
                self.assertEqual(len(L.handlers), 4)

                handler2 = str(file2)
                L.addHandler(handler2)
                self.assertEqual(len(L.handlers), 4)

                L.removeHandler(handler2)
                self.assertEqual(len(L.handlers), 3)

                L.removeHandler(pathlib.Path(file2))
                self.assertEqual(len(L.handlers), 3)

                L.removeHandler(dirpath / 'handler4.log')
                self.assertEqual(len(L.handlers), 3)

                L.removeHandler(str(dirpath / 'handler4.log'))
                self.assertEqual(len(L.handlers), 3)

                L.removeHandler(FCPath(dirpath / 'handler4.log'))
                self.assertEqual(len(L.handlers), 3)

                L.removeHandler(FCPath(file2))
                self.assertEqual(len(L.handlers), 3)

                L.removeHandler(FCPath(file1))
                self.assertEqual(len(L.handlers), 2)

                L.remove_all_handlers()

                handler = P.file_handler(dirpath / 'test')
                self.assertEqual(handler.baseFilename,
                                 os.path.abspath(dirpath / 'test.log'))

                self.assertRaises(ValueError, P.file_handler, dirpath / 'test.log',
                                  rotation='whatever')
        finally:
            if info:
                info.close()  # Required for Windows to be able to delete the tree
            if debug:
                debug.close()
            if warn:
                warn.close()
            if error:
                error.close()
            if handler:
                handler.close()
            shutil.rmtree(dirpath)

    def test_fcpath(self):
        RESET()
        URI = ('https://pds-rings.seti.org/holdings/volumes/'
               'COCIRS_1xxx/COCIRS_1001/AAREADME.TXT')      # a random remote text file
        filecache = FileCache(cache_name=None)
        handler = None
        try:
            pl = PdsLogger.get_logger('cirs')
            fcpath = FCPath(URI, filecache=filecache)
            handler = file_handler(fcpath)
            pl.add_handler(handler)
            self.assertEqual(len(pl._fcpath_by_local_abspath), 1)
            pl.warning('This is a warning')
            pl.error('This is an error')
            self.assertEqual(len(pl._fcpath_by_local_abspath), 1)
            self.assertEqual(pl._fcpath_by_local_abspath[handler.baseFilename],
                             handler.fcpath)
            self.assertEqual(len(pl._handler_by_local_abspath), 1)
            self.assertEqual(pl._handler_by_local_abspath[handler.baseFilename],
                             handler)
            text = handler.fcpath.read_text()
            recs = text.split('\n')
            self.assertEqual(recs[0], 'PDS_VERSION_ID               = PDS3')
            self.assertTrue(recs[-3].endswith('This is a warning'))
            self.assertTrue(recs[-2].endswith('This is an error'))

            with warnings.catch_warnings():  # ignore the known warning about AAREADME.TXT
                warnings.filterwarnings('ignore', message=r'.*cannot be uploaded')
                pl.remove_all_handlers()

            self.assertRaises(ValueError, file_handler, fcpath, rotation='number')

            URI = ('https://pds-rings.seti.org/holdings/volumes/'
                   'COCIRS_1xxx/COCIRS_1001/test.log')      # remote file doesn't exist
            fcpath = FCPath(URI, filecache=filecache)
            self.assertRaises(ValueError, file_handler, fcpath, rotation='midnight')

            fcpath.get_local_path().touch()
            self.assertRaises(ValueError, file_handler, fcpath, rotation='number')
        finally:
            if handler:
                handler.close()  # Required for Windows to be able to delete the tree
            filecache.delete_cache()

    def test_stream_handler(self):
        RESET()
        h = P.stream_handler()
        self.assertEqual(h.level, 2)

        h = P.stream_handler('debug')
        self.assertEqual(h.level, 10)

        h = P.stream_handler(20)
        self.assertEqual(h.level, 20)

##########################################################################################

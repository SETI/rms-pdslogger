##########################################################################################
# tests/test_pdslogger.py
##########################################################################################

import pdslogger as P
from pdslogger import LoggerError

from contextlib import redirect_stdout
import io
import os
import pathlib
import re
import shutil
import tempfile
import unittest

TIMETAG = re.compile(r'\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d\.\d+')
ELAPSED = re.compile(r'0:00:00\.\d+')

LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
          'NORMAL', 'DS_STORE', 'DOT_', 'INVISIBLE']

class Test_PdsLogger(unittest.TestCase):

    def test_log_methods(self):
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

    def test_indent(self):
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

    def test_prefix(self):
        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result))

        L1 = P.EasyLogger('foo.bar', default_prefix='PDS')
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level)

        result1 = F.getvalue().replace('PDS.foo.bar', 'pds.easylog')
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

        L1 = P.EasyLogger('foo.bar', default_prefix='foo')
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level)

        result1 = F.getvalue().replace('foo.bar', 'pds.easylog')
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

        L1 = P.EasyLogger('foo.bar', default_prefix='')
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L1.log(level, level)

        result1 = F.getvalue().replace('foo.bar', 'pds.easylog')
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result, result1)

        self.assertRaises(ValueError, P.PdsLogger, 'a.b.c')
        self.assertRaises(ValueError, P.PdsLogger, 'c.d', default_prefix='a.b')

        self.assertRaises(ValueError, P.PdsLogger, 'a.b.c.d', default_prefix='')
        self.assertRaises(ValueError, P.PdsLogger, 'c.d', default_prefix='a.b')

    def test_quietlogger(self):
        L = P.EasyLogger()
        F = io.StringIO()
        with redirect_stdout(F):
            for level in LEVELS:
                L.log(level, level)

        result = F.getvalue()
        result = ''.join(TIMETAG.split(result)).replace('easylog', 'quietlog')

        # force=True
        L1 = P.QuietLogger()
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
            L1.fatal('FATAL')
            for level in LEVELS:
                L1.log(level, level, force=False)

        result1 = F.getvalue()
        result1 = ''.join(TIMETAG.split(result1))
        self.assertEqual(result1, " | pds.quietlog || CRITICAL | FATAL\n"
                                  " | pds.quietlog || CRITICAL | CRITICAL\n")

    def test_exception(self):
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
                L.exception(e, stacktrace=True)

        result = F.getvalue()
        # print(result)
        self.assertIn(', in test_exception\n    _ = 1/0\n', result)

    def test_roots(self):
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

    def test_logged_level(self):
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

    def test_level(self):
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

    def test_pid(self):
        L = P.EasyLogger(pid=True)
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('PID')
        result = F.getvalue()
        match = re.fullmatch(r'.*easylog \| \d+ \|\| INFO \| PID', result[:-1])
        self.assertIsNotNone(match)

    def test_max_depth(self):
        L = P.EasyLogger(maxdepth=4)
        F = io.StringIO()
        with redirect_stdout(F):
            L.info('line 1')
            for t in range(4):
                L.open(f'tier {t}')
                L.debug(f'debug at tier {t}')
            self.assertRaises(ValueError, L.open, 'tier 5')

    def test_open_close(self):
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

    def test_limits(self):
        L = P.EasyLogger(timestamps=False, lognames=False, blanklines=False,
                         indent=False, limits={'debug': 4})
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

    def test_handlers(self):
        dirpath = pathlib.Path(tempfile.mkdtemp()).resolve()
        try:
            info = P.info_handler(dirpath)
            self.assertEqual(info.baseFilename, str(dirpath / 'INFO.log'))

            warn = P.warning_handler(dirpath, rotation='number')
            self.assertEqual(warn.baseFilename, str(dirpath / 'WARNINGS.log'))

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

        finally:
            shutil.rmtree(dirpath)
            pass

    def test_loggererror(self):
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

################################################################################
# pdslogger.py
#
# Mark Showalter, SETI Institute, April-September 2017
################################################################################

import sys
import os
import traceback
import logging
import logging.handlers
import datetime
import re
import glob
import shutil

try:
    import pdslogger.finder_colors as finder_colors
except ImportError:         # OK because finder_colors are not always used
    pass

try:
    from _version import __version__
except ImportError as err:
    __version__ = 'Version unspecified'


TIME_FMT = '%Y-%m-%d %H:%M:%S.%f'
MAX_DEPTH = 8           # To avoid runaway opens that lack closes

HIDDEN_STATUS = 1       # Used for messages that are never displayed but may be
                        # included in the summary

FATAL   = logging.FATAL
ERROR   = logging.ERROR
WARN    = logging.WARN
WARNING = logging.WARNING
INFO    = logging.INFO
DEBUG   = logging.DEBUG

DEFAULT_LEVEL_BY_NAME = {
    # Standard status values
    'fatal'  : logging.FATAL,   # 50
    'error'  : logging.ERROR,   # 40
    'warn'   : logging.WARN,    # 30
    'warning': logging.WARN,    # 30
    'info'   : logging.INFO,    # 20
    'debug'  : logging.DEBUG,   # 10
    'hidden' : HIDDEN_STATUS,   # 1

    # Status types defined by user
    'normal'   : logging.INFO,
    'ds_store' : logging.DEBUG,
    'dot_'     : logging.ERROR,
    'invisible': logging.WARN,
    'exception': logging.FATAL,
    'header'   : logging.INFO,
}

DEFAULT_LEVEL_TAGS = {
    logging.FATAL: 'FATAL',     # 50
    logging.ERROR: 'ERROR',     # 40
    logging.WARN : 'WARNING',   # 30
    logging.INFO : 'INFO',      # 20
    logging.DEBUG: 'DEBUG',     # 10
    HIDDEN_STATUS: 'HIDDEN',    # 1
}

DEFAULT_LIMITS_BY_NAME = {
    # Standard status values
    'fatal'  :  -1,         # -1 means no upper limit
    'error'  :  -1,
    'warning':  -1,
    'info'   : 100,
    'debug'  :   0,
    'hidden' :   0,

    # Status types defined by user
    'normal'   :  100,
    'ds_store' :   -1,
    'dot_'     :   -1,
    'invisible':   -1,
    'exception':   -1,
    'header'   :   -1,

    # The override flag allows limits to be changed at each open.
    # If override is set to False, subsequent attempts to increase a limit
    # during a call to open() will be ignored; attempts to lower a limit will
    # be respected.
    'override': True
}

# Cache of names vs. PdsLoggers
LOOKUP = {}

################################################################################
# Default handlers
################################################################################

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(HIDDEN_STATUS + 1)

def file_handler(logpath, level=HIDDEN_STATUS+1, rotation='none', suffix=''):

    assert rotation in ('none', 'number', 'midnight',
                        'ymd', 'ymdhms', 'replace'), \
        'Unrecognized rotation for log file %s: "%s"' % (logpath, rotation)

    # Create the parent directory if needed
    logpath = os.path.abspath(logpath)
    (parent, basename) = os.path.split(logpath)
    if not os.path.exists(parent):
        os.makedirs(parent)

    (rootname, ext) = os.path.splitext(basename)
    if ext == '': ext = '.log'
    prefix = os.path.join(parent, rootname)
    logpath = prefix + ext

    # Rename the previous log if rotation is 'number'
    if rotation == 'number':

        # Find the maximum version number
        version_regex = re.compile('.*' + rootname + r'_v([0-9]+)(|_\w+)' + ext)
        previous = glob.glob(prefix + '_v*' + ext)
        max_version = 0
        for filepath in previous:
            match_obj = version_regex.match(filepath)
            if match_obj:
                max_version = max(int(match_obj.group(1)), max_version)

        # Rename any files without a version number
        latest_regex = re.compile('.*' + rootname + r'(|_\w+)' + ext)
        vno_regex = re.compile('.*_v[0-9]+.*')

        previous = glob.glob(prefix + '*' + ext)
        for filepath in previous:
            match_obj = latest_regex.match(filepath)
            if not match_obj: continue
            local_suffix = match_obj.group(1)

            # A "suffix" that contains a version number should be ignored
            match_obj = vno_regex.match(local_suffix)
            if match_obj: continue

            dest = prefix + ('_v%03d' % (max_version+1)) + local_suffix + ext
            try:
                shutil.move(filepath, dest)
            except IOError:
                pass

    # Delete the previous log if rotation is 'replace'
    if rotation == 'replace' and os.path.exists(logpath):
        os.remove(logpath)

    # Construct the log file name
    if rotation == 'ymd':
        timetag = datetime.datetime.now().strftime('%Y-%m-%d')
        prefix += '_' + timetag

    elif rotation == 'ymdhms':
        timetag = datetime.datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        prefix += '_' + timetag

    if suffix:
        ext = '_' + suffix + ext

    logpath = prefix + ext

    # Create handler
    if rotation == 'midnight':
        handler = logging.handlers.TimedRotatingFileHandler(logpath,
                                                            when='midnight')
        def _rotator(source, dest):
            # This hack is required because the Python logging module is not
            # multi-processor safe, and if there are multiple processes using the
            # same log file for time rotation, they will all try to rename the
            # file at midnight, but most will crash and burn because the log file
            # is gone.
            # Further we have to rename the destination log filename to something the
            # logging module isn't expecting so that it doesn't later try to remove
            # it in another process.
            # See logging/handlers.py:392 (in Python 3.8)
            try:
                os.rename(source, dest+'_')
            except FileNotFoundError:
                pass
        handler.rotator = _rotator
    else:
        handler = logging.FileHandler(logpath, mode='a')

    # Set level
    if type(level) == str:
        level = DEFAULT_LEVEL_BY_NAME[level]

    handler.setLevel(level)

    return handler

def info_handler(path, name='INFO.log', rotation='none'):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        os.makedirs(path)

    path = os.path.join(path, name)

    return file_handler(path, level=logging.INFO, rotation=rotation)

def warning_handler(path, name='WARNINGS.log', rotation='none'):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        os.makedirs(path)

    path = os.path.join(path, name)

    return file_handler(path, level=logging.WARNING, rotation=rotation)

def error_handler(path, name='ERRORS.log', rotation='none'):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        os.makedirs(path)

    path = os.path.join(path, name)

    return file_handler(path, level=logging.ERROR, rotation=rotation)

################################################################################
# PdsLogger class
################################################################################

class PdsLogger(object):
    """Logger class adapted for PDS Ring-Moon Systems Node.

    This class defines six additional logging status aliases:
        - Status "normal" is used for any normal outcome.
        - Status "ds_store" is to be used if a ".DS_Store" file is encountered.
        - Status "dot_" is to be used if a "._*" file is encountered.
        - Status "invisible" is to be used if any other invisible file or
          directory is encountered.
        - Status "exception" is to be used when any exception is encountered.
        - Status "header" is used for headers at the beginning of tests and
          for trailers at the ends of tests.
    Each of these can be associated with a standard logging status such as
    DEBUG, INFO, WARN, ERROR or FATAL. A value of None means these messages are
    completely suppressed_by_name.

    Six "levels" of logging hierarchy (0-5) are supported. Each call to open()
    increases the hierarchy level by one. Each level in the logging hierarchy
    can be assigned its own handlers, which record logged records only for that
    level and those from deeper levels in the hierarchy.

    Headers and trailers are created at the beginning and end of each level.
    Trailers contain a summary of how many records were printed for each logging
    status.

    Each log record automatically includes a time tag, log name, status, and a
    text message. The text message can be in two parts, typically a brief
    description followed by a file path. Optionally, the process ID can also be
    included.
    """

    def __init__(self, logname, status={}, limits={}, roots=[], pid=False,
                 default_prefix='pds'):
        """Constructor for a PdsLogger.

        Input:
            logname     Name of the logger, assumed to begin "pds." Each name
                        for a logger must be globally unique.

            status      a dictionary of status names and their values. These
                        override or augment the default status values.

            limits      a dictionary indicating the upper limit on the number of
                        messages to log as a function of status name.

            roots       an optional list of character strings to suppress if
                        they appear at the beginning of file paths. Used to
                        reduce the length of log entries when, for example,
                        every file path is on the same physical volume.

            pid         True to include the process ID in each log record.

            default_prefix
                        The prefix to prepend to the logname if it is not
                        already present.
        """

        if not logname.startswith(default_prefix):
            logname = default_prefix + '.' + logname

        parts = logname.split('.')
        if len(parts) not in (2,3):
            raise ValueError('Log names must be of the form [pds.]xxx or ' +
                             '[pds.]xxx.yyy')

        if logname in LOOKUP:
            raise ValueError('PdsLogger %s already exists' % logname)

        self.logname = logname
        LOOKUP[self.logname] = self     # Save logger in cache

        self.logger = logging.getLogger(self.logname)
        self.logger.setLevel(HIDDEN_STATUS + 1)     # Default is to show
                                                    # every message not hidden
        self.handlers = []

        if type(roots) == str:
            roots = [roots]

        self.roots_ = [r.rstrip('/') + '/' for r in roots]

        self.level_by_name = DEFAULT_LEVEL_BY_NAME.copy()
        for (name, level) in status.items():
            if type(level) == str:
                level = DEFAULT_LEVEL_BY_NAME[name]
            self.level_by_name[name] = level

        self.level_tags = DEFAULT_LEVEL_TAGS.copy()
        self.default_limits_by_name = DEFAULT_LIMITS_BY_NAME.copy()

        if 'override' in limits:
            self.default_limits_by_name['override'] = limits['override']

        for (name, level) in self.level_by_name.items():
            if level not in self.level_tags:
                self.level_tags[level] = name.upper()
            if name in limits:
                self.default_limits_by_name[name] = limits[name]
            if name not in self.default_limits_by_name:
                self.default_limits_by_name[name] = -1

        self.titles = []
        self.start_times = []
        self.limits_by_name      = []
        self.counters_by_name    = []
        self.suppressed_by_name  = []
        self.counters_by_level   = []
        self.suppressed_by_level = []
        self.local_handlers      = []

        if pid:
            self.pid = os.getpid()
            self.pidstr = '|%6d ' % self.pid
        else:
            self.pid = 0
            self.pidstr = ''

    def get_level(self):
        return len(self.titles)

    def add_root(self, roots):
        """Add a root path, or list of root paths."""

        if type(roots) == str:
            roots = [roots]

        for root_ in roots:
            root_ = root_.rstrip('/') + '/'
            if root_ not in self.roots_:
                self.roots_.append(root_)

    def replace_root(self, roots):
        """Replace the existing root(s) with one or more new paths."""

        self.roots_ = []
        self.add_root(roots)

    def set_limit(self, name, limit):
        """Set upper limit on the number of messages with this status name.
        """

        if self.limits_by_name:
            self.limits_by_name[-1][name] = limit
        else:
            self.default_limits_by_name[name] = limit

    def add_handler(self, handlers):
        """Add one or more global handlers to this PdsLogger."""

        if type(handlers) not in (list, tuple):
            handlers = [handlers]

        for handler in handlers:
            self.logger.addHandler(handler)

            if handler not in self.handlers:
                self.handlers.append(handler)

    def remove_handler(self, handlers):
        """Remove one or more global handlers from this PdsLogger."""

        if type(handlers) not in (list, tuple):
            handlers = [handlers]

        for handler in handlers:
            self.logger.removeHandler(handler)  # no exception if not present

            if handler in self.handlers:
                self.handlers.remove(handler)

    def remove_all_handlers(self):
        """Remove all the global handlers from this PdsLogger."""

        for handler in self.handlers:
            self.logger.removeHandler(handler)  # no exception if not present
            self.handlers.remove(handler)

        self.logger.handlers = []

    def replace_handler(self, handlers):
        """Replace the existing global handlers with one or more new handlers.
        """

        handlers = list(self.logger.handlers)
        for handler in handlers:
            self.logger.removeHandler(handler)

        self.handlers = []

        self.add_handler(handlers)

    def logpath(self, abspath):
        """Strip the leading root from a file path."""

        for root_ in self.roots_:
            if abspath.startswith(root_):
                return abspath[len(root_):]

        return abspath

    def logstatus(self, status):
        """Convert the status as a name or number to a name."""

        if type(status) == str:
            return status

        return self.level_tags[status].lower()

    @staticmethod
    def get_logger(logname):
        """Return the PdsLogger associated with the given name."""

        try:
            return LOOKUP['pds.' + logname]
        except KeyError:
            return LOOKUP[logname]

    def open(self, title, abspath='', limits={}, handler=[]):
        """Begin a new set of tests at a new level in the hierarchy, possibly
        including one or more local handlers, which are managed separately from
        the global handlers."""

        # Increment the hierarchy depth
        depth = len(self.titles)
        if depth == MAX_DEPTH:
            raise ValueError('Maximum logging hierarchy depth has been reached')
            sys.exit(1)

        if abspath:
            title += ': ' + self.logpath(abspath)
        self.titles.append(title)

        time = datetime.datetime.now()
        timetag = time.strftime(TIME_FMT)
        self.start_times.append(time)

        # Save any level-specific handlers if necessary
        self.local_handlers.append([])

        if type(handler) in (list, tuple):
            handlers = handler
        else:
            handlers = [handler]

        # Get list of full paths to the log files
        logfiles = [h.baseFilename for h in self.handlers if
                                            isinstance(h, logging.FileHandler)]

        # Add the new handlers if unique
        for handler in handlers:
            if handler in self.handlers: continue
            if (isinstance(handler, logging.FileHandler) and
                handler.baseFilename in logfiles): continue

            self.logger.addHandler(handler)
            self.local_handlers[-1].append(handler)
            self.handlers.append(handler)

        # Set the level-specific limits
        if self.limits_by_name:
            self.limits_by_name.append(self.limits_by_name[-1].copy())
        else:
            self.limits_by_name.append(self.default_limits_by_name.copy())

        override = self.limits_by_name[-1]['override']
        for (name, limit) in limits.items():
            if name == 'override':
                self.limits_by_name[-1][name] &= limit
            elif override:
                self.limits_by_name[-1][name] = limit
            else:
                # Only a decrease is allowed
                if limit < 0: continue

                current_limit = self.limits_by_name[-1][name]
                if current_limit < 0:
                    self.limits_by_name[-1][name] = limit
                else:
                    self.limits_by_name[-1][name] = min(limit, current_limit)

        zeros = {}
        for name in self.level_by_name:
            zeros[name] = 0

        self.counters_by_name.append(zeros.copy())
        self.suppressed_by_name.append(zeros)

        zeros = {}
        for level in self.level_tags:
            zeros[level] = 0

        self.counters_by_level.append(zeros.copy())
        self.suppressed_by_level.append(zeros)

        # Write header
        self.logger_log(self.level_by_name['header'],
            '%s | %s %s|%s| %s | %s' %
            (timetag, self.logname, self.pidstr, depth*'-', 'HEADER', title))

    def log(self, status, message, abspath='', force=False):
        """Log one record.

        status = logging status;
        message = message to print;
        abspath = absolute path of the relevant file, if any;
        force = True to force message reporting even if the relevant limit has
                been reached.
        """

        # Determine the status
        name = self.logstatus(status)
        level = self.level_by_name[name]
        tag = self.level_tags[level]
        depth = len(self.titles)

        # Count the messages with this status
        if depth > 0:
            self.counters_by_name[-1][name] += 1
            self.counters_by_level[-1][level] += 1

        # Log message if necessary
        if depth > 0:
            limit = self.limits_by_name[-1][name]
            if limit < 0:
                force = True
        else:
            force = True

        if force or self.counters_by_name[-1][name] <= limit:
            timetag = datetime.datetime.now().strftime(TIME_FMT)
            if abspath:
                message += ': ' + self.logpath(abspath)

            self.logger_log(level, '%s | %s %s|%s| %s | %s' %
                (timetag, self.logname, self.pidstr, depth*'-', tag, message))

        # Otherwise, count suppressed_by_name messages
        else:
            self.suppressed_by_name[-1][name] += 1
            self.suppressed_by_level[-1][level] += 1

            # Note first suppression
            if self.suppressed_by_name[-1][name] == 1 and limit != 0:
                timetag = datetime.datetime.now().strftime(TIME_FMT)

                tag = tag.rstrip()
                if name.upper() == tag:
                    info = tag
                else:
                    info = name + ' ' + tag
                message = 'Additional %s messages suppressed' % info
                self.logger_log(level, '%s | %s %s|%s| %s | %s' %
                  (timetag, self.logname, self.pidstr, depth*'-', tag, message))

    def summarize(self):
        """Return (number of errors, number of warnings, total number of tests).
        """

        fatal = 0
        errors = 0
        warnings = 0
        tests = 0
        for (level, count) in self.counters_by_level[-1].items():
            if level >= logging.FATAL:
                fatal += count
            if level >= logging.ERROR:
                errors += count
            if level >= logging.WARNING:
                warnings += count

            tests += count

        errors -= fatal
        warnings -= errors

        return (fatal, errors, warnings, tests)

    def close(self):
        """Close the log at its current hierarchy depth.

        Return (number of errors, number of warnings, total number of tests).
        """

        depth = len(self.titles)

        # Get new time tag
        time = datetime.datetime.now()
        timetag = time.strftime(TIME_FMT)

        # Summarize results
        self.logger_log(self.level_by_name['header'],
                        '%s | %s %s|%s| %s | Completed: %s' %
                        (timetag, self.logname, self.pidstr, (depth-1)*'-',
                         'SUMMARY', self.titles[-1]))

        self.logger_log(self.level_by_name['header'],
                        '%s | %s %s|%s| %s | Elapsed time = %s' %
                        (timetag, self.logname, self.pidstr, (depth-1)*'-',
                         'SUMMARY', str(time - self.start_times[-1])))

        # Log message counts by error level
        levels = list(self.counters_by_level[-1].keys())
        levels.sort()
        for level in levels:
            count = self.counters_by_level[-1][level]
            suppressed = self.suppressed_by_level[-1][level]
            if count + suppressed == 0: continue

            tag = self.level_tags[level].rstrip()
            if suppressed == 0:
                plural = '' if count == 1 else 's'
                message = '%d %s message%s' % (count, tag, plural)
            else:
                unsuppressed = count - suppressed
                plural = '' if unsuppressed == 1 else 's'
                message = '%d %s message%s reported of %d total' % \
                          (unsuppressed, tag, plural, count)

            self.logger_log(max(level, self.level_by_name['header']),
                            '%s | %s %s|%s| %s | %s' %
                            (timetag, self.logname, self.pidstr, (depth-1)*'-',
                             'SUMMARY', message))

        # Blank line
        self.logger_log(self.level_by_name['header'], '')

        # Transfer the totals to the hierarchy depth above
        if depth > 1:
            for (name, count) in self.counters_by_name[-1].items():
                self.counters_by_name[-2][name] += count
                self.suppressed_by_name[-2][name] += \
                                            self.suppressed_by_name[-1][name]

            for (level,count) in self.counters_by_level[-1].items():
                self.counters_by_level[-2][level] += count
                self.suppressed_by_level[-2][level] += \
                                            self.suppressed_by_level[-1][level]

        # Determine values to return
        (fatal, errors, warnings, tests) = self.summarize()

        # Back up one level in the hierarchy
        self.titles      = self.titles[:-1]
        self.start_times = self.start_times[:-1]
        self.limits_by_name      = self.limits_by_name[:-1]
        self.counters_by_name    = self.counters_by_name[:-1]
        self.suppressed_by_name  = self.suppressed_by_name[:-1]
        self.counters_by_level   = self.counters_by_level[:-1]
        self.suppressed_by_level = self.suppressed_by_level[:-1]

        # List the handlers to close at this level
        # If this is the top level, include the global handlers
        handlers = self.local_handlers[-1]
        if len(self.local_handlers) == 1:
            handlers += self.handlers

        for handler in handlers:
            if handler in self.handlers:
                self.handlers.remove(handler)
                self.logger.removeHandler(handler)

            # If the xattr module has been imported on a Mac, set the colors of
            # the log files to indicate outcome.
            try:        # in case the finder_colors module was not imported
                logfile = handler.baseFilename
                if fatal:
                    finder_colors.set_color(logfile, 'violet')
                elif errors:
                    finder_colors.set_color(logfile, 'red')
                elif warnings:
                    finder_colors.set_color(logfile, 'yellow')
                else:
                    finder_colors.set_color(logfile, 'green')
            except (AttributeError, NameError):
                pass

        self.local_handlers = self.local_handlers[:-1]

        return (fatal, errors, warnings, tests)

    def debug(self, message, abspath='', force=False):
        self.log('debug', message, abspath, force)

    def info(self, message, abspath='', force=False):
        self.log('info', message, abspath, force)

    def warn(self, message, abspath='', force=False):
        self.log('warn', message, abspath, force)

    def error(self, message, abspath='', force=False):
        self.log('error', message, abspath, force)

    def fatal(self, message, abspath='', force=False):
        self.log('fatal', message, abspath, force)

    def normal(self, message, abspath='', force=False):
        self.log('normal', message, abspath, force)

    def ds_store(self, message, abspath='', force=False):
        self.log('ds_store', message, abspath, force)

    def dot_underscore(self, message, abspath='', force=False):
        self.log('dot_', message, abspath, force)

    def invisible(self, message, abspath='', force=False):
        self.log('invisible', message, abspath, force)

    def hidden(self, message, abspath='', force=False):
        self.log('hidden', message, abspath, force)

    def exception(self, e, abspath='', stacktrace=True):
        """Log an Exception or KeyboardInterrupt."""

        if type(e) == KeyboardInterrupt:
            self.fatal('**** Interrupted by user')
            raise e

        (etype, value, tb) = sys.exc_info()
        if etype is None:
            return                      # Exception was already handled

        self.log('exception', '**** ' + etype.__name__ + ' ' + str(value),
                              abspath, force=True)

        if stacktrace:
            self.logger_log(self.level_by_name['exception'],
                            ''.join(traceback.format_tb(tb)))

    def blankline(self):
        self.logger.log(self.level_by_name['header'], '')

    def logger_log(self, level, message):
        self.logger.log(level, message)

class EasyLogger(PdsLogger):
    """Simple subclass of PdsLogger that prints all messages to the terminal."""

    def __init__(self, logname='easylog', status={}, limits={}, roots=[],
                 pid=False, default_prefix='pds'):

        global LOOKUP

        # Override the test regarding whether this logger already exists
        saved_lookup = LOOKUP.copy()
        LOOKUP.clear()
        try:
            self.pdslogger = PdsLogger(logname, status, limits, roots, pid,
                                       default_prefix)
        finally:
            for (key, value) in saved_lookup.items():
                LOOKUP[key] = value

        self.logname       = self.pdslogger.logname
        self.logger        = self.pdslogger.logger
        self.handlers      = self.pdslogger.handlers
        self.roots_        = self.pdslogger.roots_
        self.level_by_name = self.pdslogger.level_by_name
        self.level_tags    = self.pdslogger.level_tags
        self.default_limits_by_name = self.pdslogger.default_limits_by_name
        self.titles              = self.pdslogger.titles
        self.start_times         = self.pdslogger.start_times
        self.limits_by_name      = self.pdslogger.limits_by_name
        self.counters_by_name    = self.pdslogger.counters_by_name
        self.suppressed_by_name  = self.pdslogger.suppressed_by_name
        self.counters_by_level   = self.pdslogger.counters_by_level
        self.suppressed_by_level = self.pdslogger.suppressed_by_level
        self.local_handlers      = self.pdslogger.local_handlers
        self.pid                 = self.pdslogger.pid
        self.pidstr              = self.pdslogger.pidstr

    def replace_root(self, roots):
        self.pdslogger.replace_root(roots)
        self.roots_ = self.pdslogger.roots_

    def remove_all_handlers(self):
        self.pdslogger.remove_all_handlers()
        self.handlers = self.pdslogger.handlers

    def logger_log(self, level, message):
        print(message)

class NullLogger(EasyLogger):
    """Supports the full PdsLogger interface but does no logging."""

    def logger_log(self, level, message):
        pass

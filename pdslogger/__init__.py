##########################################################################################
# pdslogger.py
##########################################################################################
"""PDS RMS Node enhancements to the Python logger module."""

import datetime
import logging
import logging.handlers
import os
import pathlib
import re
import sys
import traceback
import warnings

from collections import defaultdict

try:
    import pdslogger.finder_colors as finder_colors
except ImportError:     # pragma: no cover
    # Exception is OK because finder_colors are not always used
    pass

try:
    from ._version import __version__
except ImportError:
    __version__ = 'Version unspecified'

_TIME_FMT = '%Y-%m-%d %H:%M:%S.%f'

FATAL   = logging.FATAL
ERROR   = logging.ERROR
WARN    = logging.WARN
WARNING = logging.WARNING
INFO    = logging.INFO
DEBUG   = logging.DEBUG
HIDDEN  = 1     # Used for messages that are never displayed but might be summarized

_LEVEL_NAME_ALIASES = {
    'warn': 'warning',
    'critical': 'fatal',
}

def _repair_level_name(name):
    name = name.lower()
    name = _LEVEL_NAME_ALIASES.get(name, name)
    return name

_DEFAULT_LEVEL_BY_NAME = {
    # Standard level values
    'fatal'   : logging.FATAL,  # 50
    'error'   : logging.ERROR,  # 40
    'warning' : logging.WARN,   # 30
    'info'    : logging.INFO,   # 20
    'debug'   : logging.DEBUG,  # 10
    'hidden'  : HIDDEN,         #  1

    # Additional level values defined for every PdsLogger
    'normal'   : logging.INFO,
    'ds_store' : logging.DEBUG,
    'dot_'     : logging.ERROR,
    'invisible': logging.WARN,
    'exception': logging.FATAL,
    'header'   : logging.INFO,
}

_DEFAULT_LEVEL_NAMES = {
    logging.FATAL: 'fatal',     # 50
    logging.ERROR: 'error',     # 40
    logging.WARN : 'warning',   # 30
    logging.INFO : 'info',      # 20
    logging.DEBUG: 'debug',     # 10
    HIDDEN       : 'hidden',    #  1
}

_DEFAULT_LIMITS_BY_NAME = {     # we're treating all as unlimited by default now
}

# Cache of names vs. PdsLoggers
_LOOKUP = {}

class LoggerError(Exception):
    """For an exception of this class, `logger.exception()` will write a message into the
    log with the user-specified level.

    In addition, no traceback will be included in the log.
    """

    def __init__(self, message, filepath='', *, force=False, level='error'):
        """Constructor.

        Parameters:
            message (str or Exception):
                Text of the message as a string. If an Exception object is provided, the
                message is derived from this error.
            filepath (str or pathlib.Path, optional):
                File path to include in the message. If not specified, the `filepath`
                appearing in the call to `exception()` will be used.
            force (bool, optional):
                True to force the message to be logged even if the logging level is above
                the level of "warn".
            level (int or str, optional):
                The level or level name for a record to enter the log.
            error (Exception, optional):
                If specified, the class and message string of this error are included in
                the new error message.
        """

        if isinstance(message, Exception):
            self.message = type(message).__name__ + '(' + str(message) + ')'
        else:
            self.message = str(message)

        self.filepath = filepath
        self.force = force
        self.level = level

    def __str__(self):
        if self.filepath:
            return self.message + ': ' + str(self.filepath)
        return self.message

##########################################################################################
# Handlers
##########################################################################################

STDOUT_HANDLER = logging.StreamHandler(sys.stdout)
STDOUT_HANDLER.setLevel(HIDDEN + 1)

def stream_handler(level=HIDDEN+1, stream=sys.stdout):
    """Stream handler for a PdsLogger, e.g., for directing messages to the terminal.

    Parameters:
        level (int or str, optional):
            The minimum logging level at which to log messages; either an int or one of
            "fatal", "error", "warn", "warning", "info", "debug", or "hidden".
        stream (stream, optional):
            An output stream, defaulting to the terminal via sys.stdout.
    """

    if isinstance(level, str):
        level = _DEFAULT_LEVEL_BY_NAME[_repair_level_name(level)]

    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    return handler


def file_handler(logpath, level=HIDDEN+1, rotation='none', suffix=''):
    """File handler for a PdsLogger.

    Parameters:
        logath (str or pathlib.Path):
            The path to the log file.
        level (int or str):
            The minimum logging level at which to log messages; either an int or one of
            "fatal", "error", "warn", "warning", "info", "debug", or "hidden".
        rotation (str, optional):
            Log file rotation method, one of:

            * "none": No rotation; append to an existing log of the same name.
            * "number": Move an existing log file to one of the same name with a version
              number ("_v" followed by an integer suffix of at least three digits) before
              the extension.
            * "midnight": Each night at midnight, append the date to the log file name and
              start a new log.
            * "ymd": Append the current date in the form "_yyyy-mm-dd" to each log file
              name (before the ".log" extension).
            * "ymdhms": Append the current date and time in the form
              "_yyyy-mm-ddThh-mm-ss" to each log file name (before the ".log" extension).
            * "replace": Replace this new log with any pre-existing log of the same name.

        suffix (str, optional):
            Append this suffix string to the log file name after any date and before the
            extension.

        Returns:
            logging.FileHandler: FileHandler with the specified properties.

        Raises:
            ValueError: Invalid  `rotation`.
            KeyError: Invalid `level` string.
    """

    if rotation not in {'none', 'number', 'midnight', 'ymd', 'ymdhms', 'replace'}:
        raise ValueError(f'Unrecognized rotation for log file {logpath}: "{rotation}"')

    if isinstance(level, str):
        level = _DEFAULT_LEVEL_BY_NAME[_repair_level_name(level)]

    # Create the parent directory if needed
    logpath = pathlib.Path(logpath)
    logpath.parent.mkdir(parents=True, exist_ok=True)

    if not logpath.suffix:
        logpath = logpath.with_suffix('.log')

    # Rename the previous log if rotation is "number"
    if rotation == 'number':

        if logpath.exists():
            # Rename an existing log to one greater than the maximum numbered version
            max_version = 0
            regex = re.compile(logpath.stem + r'_v([0-9]+)' + logpath.suffix)
            for filepath in logpath.parent.glob(logpath.stem + '_v*' + logpath.suffix):
                match = regex.match(filepath.name)
                if match:
                    max_version = max(int(match.group(1)), max_version)

            basename = logpath.stem + '_v%03d' % (max_version+1) + logpath.suffix
            logpath.rename(logpath.parent / basename)

    # Delete the previous log if rotation is 'replace'
    elif rotation == 'replace':
        if logpath.exists():
            logpath.unlink()

    # Construct a dated log file name
    elif rotation == 'ymd':
        timetag = datetime.datetime.now().strftime('%Y-%m-%d')
        logpath = logpath.with_stem(logpath.stem + '_' + timetag)

    elif rotation == 'ymdhms':
        timetag = datetime.datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        logpath = logpath.with_stem(logpath.stem + '_' + timetag)

    if suffix:
        basename = logpath.stem + '_' + suffix.lstrip('_') + logpath.suffix
        logpath = logpath.parent / basename

    # Create handler
    if rotation == 'midnight':
        handler = logging.handlers.TimedRotatingFileHandler(logpath, when='midnight')

        def _rotator(source, dest):
            # This hack is required because the Python logging module is not
            # multi-processor safe, and if there are multiple processes using the same log
            # file for time rotation, they will all try to rename the file at midnight,
            # but most will crash and burn because the log file is gone.
            # Furthermore, we have to rename the destination log filename to something the
            # logging module isn't expecting so that it doesn't later try to remove it in
            # another process.
            # See logging/handlers.py:392 (in Python 3.8)
            try:
                os.rename(source, dest + '_')
            except FileNotFoundError:
                pass
        handler.rotator = _rotator
    else:
        handler = logging.FileHandler(logpath, mode='a')

    handler.setLevel(level)
    return handler


def info_handler(parent, name='INFO.log', *, rotation='none'):
    """Quick creation of an "info"-level file handler.

    Parameters:
        parent (str or pathlib.Path):
            Path to the parent directory.
        name (str, optional):
            Basename of the file handler.
        rotation (str, optional):
            Log file rotation method, one of:

            * "none": No rotation; append to an existing log of the same name.
            * "number": Move an existing log file to one of the same name with a version
              number ("_v" followed by an integer suffix of at least three digits) before
              the extension.
            * "midnight": Each night at midnight, append the date to the log file name and
              start a new log.
            * "ymd": Append the current date in the form "_yyyy-mm-dd" to each log file
              name (before the ".log" extension).
            * "ymdhms": Append the current date and time in the form
              "_yyyy-mm-ddThh-mm-ss" to each log file name (before the ".log" extension).
            * "replace": Replace this new log with any pre-existing log of the same name.

        Returns:
            logging.FileHandler: FileHandler with the specified properties.

        Raises:
            ValueError: Invalid `rotation`.
    """

    parent = pathlib.Path(parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    return file_handler(parent / name, level=INFO, rotation=rotation)


def warning_handler(parent, name='WARNINGS.log', *, rotation='none'):
    """Quick creation of a "warning"-level file handler.

    Parameters:
        parent (str or pathlib.Path):
            Path to the parent directory.
        name (str, optional):
            Basename of the file handler.
        rotation (str, optional):
            Log file rotation method, one of:

            * "none": No rotation; append to an existing log of the same name.
            * "number": Move an existing log file to one of the same name with a version
              number ("_v" followed by an integer suffix of at least three digits) before
              the extension.
            * "midnight": Each night at midnight, append the date to the log file name and
              start a new log.
            * "ymd": Append the current date in the form "_yyyy-mm-dd" to each log file
              name (before the ".log" extension).
            * "ymdhms": Append the current date and time in the form
              "_yyyy-mm-ddThh-mm-ss" to each log file name (before the ".log" extension).
            * "replace": Replace this new log with any pre-existing log of the same name.

        Returns:
            logging.FileHandler: FileHandler with the specified properties.

        Raises:
            ValueError: Invalid `rotation`.
    """

    parent = pathlib.Path(parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    return file_handler(parent / name, level=WARNING, rotation=rotation)


def error_handler(parent, name='ERRORS.log', *, rotation='none'):
    """Quick creation of an "error"-level file handler.

    Parameters:
        parent (str or pathlib.Path):
            Path to the parent directory.
        name (str, optional):
            Basename of the file handler.
        rotation (str, optional):
            Log file rotation method, one of:

            * "none": No rotation; append to an existing log of the same name.
            * "number": Move an existing log file to one of the same name with a version
              number ("_v" followed by an integer suffix of at least three digits) before
              the extension.
            * "midnight": Each night at midnight, append the date to the log file name and
              start a new log.
            * "ymd": Append the current date in the form "_yyyy-mm-dd" to each log file
              name (before the ".log" extension).
            * "ymdhms": Append the current date and time in the form
              "_yyyy-mm-ddThh-mm-ss" to each log file name (before the ".log" extension).
            * "replace": Replace this new log with any pre-existing log of the same name.

        Returns:
            logging.FileHandler: FileHandler with the specified properties.

        Raises:
            ValueError: Invalid `rotation`.
    """

    parent = pathlib.Path(parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    return file_handler(parent / name, level=ERROR, rotation=rotation)

##########################################################################################
# PdsLogger class
##########################################################################################

class PdsLogger(logging.Logger):
    """Logger class adapted for PDS Ring-Moon Systems Node.

    This class defines six additional logging level aliases:

    * `"normal"` is used for any normal outcome.
    * `"ds_store"` is to be used if a ".DS_Store" file is encountered.
    * `"dot_"` is to be used if a "._*" file is encountered.
    * `"invisible"` is to be used if any other invisible file or directory is encountered.
    * `"exception"` is to be used when any exception is encountered.
    * `"header"` is used for headers at the beginning of tests and for trailers at the
      ends of tests.

    Additional aliases are definable by the user. These aliases are independent of the
    "levels" normally associated with logging in Python. For example, the default level of
    alias "normal" is 20, which is the same as that of "info" messages. The user can
    specify the numeric level for each user-defined alias, and multiple aliases may use
    the same level. A level of None or HIDDEN means that messages with this alias are
    always suppressed.

    Users can also specify a limit on the number of messages that can be associated with
    an alias. For example, if the limit on "info" messages is 100, then log messages after
    the hundredth will be suppressed, although the number of suppressed messages will
    still be tracked. At the end of the log, a tally of the messages associated with each
    alias is printed, including the number suppressed if the limit was exceeded.

    A hierarchy is supported within logs. Each call to logger.open() initiates a new
    context having its own new limits, logging level, and, optionally, its own handlers.
    Using this capability, a program that performs multiple tasks can generate one global
    log and also a separate log for each task. Each call to open() writes a section header
    into the log and each call to close() inserts a tally of messages printed at that and
    deeper tiers of the hierarchy. Alternatively, logger.open() can be used as a context
    manager using "with".

    By default, each log record automatically includes a time tag, log name, level, and a
    text message. The text message can be in two parts, typically a brief description
    followed by a file path. Optionally, the process ID can also be included. Options are
    provided to control which of these components are included.

    In the Macintosh Finder, log files are color-coded by the most severe message
    encountered within the file: green for info, yellow for warnings, red for errors, and
    violet for fatal errors.

    If a PdsLogger has not been assigned any handlers, it prints messages to the terminal.
    """

    _LOGGER_IS_FAKE = False     # Used by EasyLogger below

    def __init__(self, logname, *, default_prefix='pds.', levels={}, limits={}, roots=[],
                 level=HIDDEN+1, timestamps=True, digits=6, lognames=True, pid=False,
                 indent=True, blanklines=True, colors=True, maxdepth=6):
        """Constructor for a PdsLogger.

        Parameters:
            logname (str):
                Name of the logger. Each name for a logger must be globally unique.
            default_prefix (str, optional)
                The prefix to prepend to the logname if it is not already present. By
                default, this is "pds.".
            levels (dict, optional):
                A dictionary of level names and their values. These override or augment
                the default level values.
            limits (dict, optional):
                A dictionary indicating the upper limit on the number of messages to log
                as a function of level name.
            roots (list[str or pathlib.Path], optional):
                Character strings to suppress if they appear at the beginning of file
                paths. Used to reduce the length of log entries when, for example, every
                file path is on the same physical volume.
            level (int or str, optional):
                The minimum level or level name for a record to enter the log.
            timestamps (bool, optional):
                True to include timestamps in the log records.
            digits (int, optional):
                Number of fractional digits in the seconds field of the timestamp.
            lognames (bool, optional):
                True to include the name of the logger in the log records.
            pid (bool, optional):
                True to include the process ID in each log record.
            indent (bool, optional):
                True to include a sequence of dashes in each log record to provide a
                visual indication of the tier in a logging hierarchy.
            blanklines (bool, optional):
                True to include a blank line in log files when a tier in the hierarchy is
                closed; False otherwise.
            colors (bool, optional):
                True to color-code any log files generated, for Macintosh only.
            maxdepth (int, optional):
                Maximum depth of the logging hierarchy, needed to prevent unlimited
                recursion.
        """

        logname = self._full_logname(logname, default_prefix)

        self._logname = logname
        if self._LOGGER_IS_FAKE:
            self._logger = None
        else:
            if logname in _LOOKUP:                              # pragma: no cover
                raise ValueError(f'PdsLogger {self._logname} already exists')
            _LOOKUP[self._logname] = self                       # Save logger in cache
            self._logger = logging.getLogger(self._logname)

        # Merge the dictionary of levels and their names
        self._level_by_name = _DEFAULT_LEVEL_BY_NAME.copy()     # name -> level
        self._level_names = _DEFAULT_LEVEL_NAMES.copy()         # level -> primary name
        self._merge_level_names(levels)

        # Define roots
        if isinstance(roots, str):
            roots = [roots]
        self._roots = []
        self.add_root(*roots)

        # Fill in default format values
        if level is None:
            level = level or HIDDEN + 1
        if timestamps is None:
            timestamps = True
        if digits is None:
            digits = 6
        if lognames is None:
            lognames = True
        if pid is None:
            pid = False
        if indent is None:
            indent = True
        if blanklines is None:
            blanklines = True
        if colors is None:
            colors = True
        if maxdepth is None:
            maxdepth = 6

        # Save log record format info
        self._timestamps = bool(timestamps)
        self._digits = digits
        self._lognames = bool(lognames)
        self._pid = os.getpid() if pid else 0
        self._indent = bool(indent)
        self._blanklines = bool(blanklines)
        self._colors = bool(colors)
        self._maxdepth = maxdepth

        self._handlers = []         # complete list of handlers across all tiers
        self._suppressions_logged = set()   # level names having had a suppression message

        # Support for multiple tiers in hierarchy
        self._titles              = [self._logname]
        self._start_times         = [datetime.datetime.now()]
        self._counters_by_name    = [defaultdict(int)]
        self._suppressed_by_name  = [defaultdict(int)]
        self._local_handlers      = [[]]    # handlers at this tier but not above

        self._min_levels          = [0]
        self.set_level(level)

        self._limits_by_name = [defaultdict(lambda: -1)]
        self._limits_by_name[-1].update(_DEFAULT_LIMITS_BY_NAME)
        for level_name, level_num in limits.items():
            self.set_limit(level_name, level_num)

    @staticmethod
    def get_logger(logname, *, default_prefix='pds.', levels={}, limits={}, roots=[],
                   level=None, timestamps=None, digits=None, lognames=None, pid=None,
                   indent=None, blanklines=None, colors=None, maxdepth=None):
        """Return the current logger by this name if it already exists; otherwise,
        construct and return a new PdsLogger.

        Parameters:
            logname (str):
                Name of the logger.
            default_prefix (str, optional)
                The prefix to prepend to the logname if it is not already present. By
                default, this is "pds.".
            levels (dict, optional):
                A dictionary of level names and their values. These override or augment
                the default level values.
            limits (dict, optional):
                A dictionary indicating the upper limit on the number of messages to log
                as a function of level name.
            roots (list[str or pathlib.Path], optional):
                Character strings to suppress if they appear at the beginning of file
                paths. Used to reduce the length of log entries when, for example, every
                file path is on the same physical volume.
            level (int or str, optional):
                The minimum level or level name for a record to enter the log.
            timestamps (bool, optional):
                True to include timestamps in the log records.
            digits (int, optional):
                Number of fractional digits in the seconds field of the timestamp.
            lognames (bool, optional):
                True to include the name of the logger in the log records.
            pid (bool, optional):
                True to include the process ID in each log record.
            indent (bool, optional):
                True to include a sequence of dashes in each log record to provide a
                visual indication of the tier in a logging hierarchy.
            blanklines (bool, optional):
                True to include a blank line in log files when a tier in the hierarchy is
                closed; False otherwise.
            colors (bool, optional):
                True to color-code any log files generated, for Macintosh only.
            maxdepth (int, optional):
                Maximum depth of the logging hierarchy, needed to prevent unlimited
                recursion.
        """

        logname = PdsLogger._full_logname(logname, default_prefix)
        if logname in _LOOKUP:
            logger = _LOOKUP[logname]
            logger.set_format(level=level, timestamps=timestamps, digits=digits,
                              lognames=lognames, pid=pid, indent=indent,
                              blanklines=blanklines, colors=colors, maxdepth=maxdepth)
            logger._merge_level_names(levels)

            for name, value in limits.items():
                logger.set_limit(name, value)

            roots = [roots] if isinstance(roots, str) else roots
            for name in roots:
                logger.add_root(name, value)

            return logger

        return PdsLogger(logname, levels=levels, limits=limits, roots=roots, level=level,
                         timestamps=timestamps, digits=digits, lognames=lognames, pid=pid,
                         indent=indent, blanklines=blanklines, colors=colors,
                         maxdepth=maxdepth)

    @staticmethod
    def _full_logname(logname, default_prefix='pds.'):
        """The full log name with the prefix pre-pended if necessary."""

        if default_prefix:
            default_prefix = default_prefix.rstrip('.') + '.'   # exactly one trailing dot
            if not logname.startswith(default_prefix):
                logname = default_prefix + logname

        parts = logname.split('.')
        if len(parts) not in (2, 3):
            raise ValueError(f'Log names must be of the form [{default_prefix}]xxx or '
                             f'[{default_prefix}]xxx.yyy')

        return logname

    def _merge_level_names(self, levels):
        """Merge the given dictionary mapping level names to numbers into the internal
        dictionaries.
        """

        for level_name, level_num in levels.items():
            if isinstance(level_num, str):
                level_num = _DEFAULT_LEVEL_BY_NAME[_repair_level_name(level_num)]
            self._level_by_name[level_name] = level_num

        for level_name, level_num in self._level_by_name.items():
            if level_num not in self._level_names:
                self._level_names[level_num] = level_name

    def set_level(self, level):
        """Set the level of messages for the current tier in the logger's hierarchy.

        Parameters;
            level (int or str, optional):
                The minimum level of level name for a record to enter the log.
        """

        if isinstance(level, str):
            self._min_levels[-1] = self._level_by_name[_repair_level_name(level)]
        else:
            self._min_levels[-1] = level

        if self._logger:
            self._logger.setLevel(self._min_levels[-1])

    def set_format(self, *, level=None, timestamps=None, digits=None, lognames=None,
                   pid=None, indent=None, blanklines=None, colors=None, maxdepth=None):
        """Set or modify the formatting and other properties of this PdsLogger.

        Parameters:
            level (int or str, optional):
                The minimum level of level name for a record to enter the log.
            timestamps (bool, optional):
                True or False, defining whether to include a timestamp in each log record.
            digits (int, optional):
                Number of fractional digits in the seconds field of the timestamp.
            lognames (bool, optional):
                True or False, defining whether to include the name of the logger in each
                log record.
            pid (bool, optional):
                True or False, defining whether to include the process ID in each log
                record.
            indent (bool, optional):
                True or False, defining whether to include a sequence of dashes in each
                log record to provide a visual indication of the tier in a logging
                hierarchy.
            blanklines (bool, optional):
                True or False, defining whether to include a blank line in log files when
                a tier in the hierarchy is closed.
            colors (bool, optional):
                True or False, defining whether to color-code the log files generated, for
                Macintosh only.
            maxdepth (int, optional):
                Maximum depth of the logging hierarchy, needed to prevent unlimited
                recursion.
        """

        if level is not None:
            self.set_level(level)
        if timestamps is not None:
            self._timestamps = bool(timestamps)
        if digits is not None:
            self._digits = digits
        if lognames is not None:
            self._lognames = bool(lognames)
        if pid is not None:
            self._pid = os.getpid() if pid else 0
        if indent is not None:
            self._indent = bool(indent)
        if blanklines is not None:
            self._blanklines = bool(blanklines)
        if colors is not None:
            self._colors = bool(colors)
        if maxdepth is not None:
            self._maxdepth = maxdepth

    def set_limit(self, name, limit):
        """Set the upper limit on the number of messages with this level name.

        A limit of -1 implies no limit.
        """

        self._limits_by_name[-1][_repair_level_name(name)] = limit

    def add_root(self, *roots):
        """Add one or more paths to the set of root paths.

        When a root path appears at the beginning of a logged file path, the leading
        portion is suppressed.
        """

        for root_ in roots:
            root_ = str(root_).rstrip('/') + '/'
            if root_ not in self._roots:
                self._roots.append(root_)

        self._roots.sort(key=lambda x: (-len(x), x))    # longest patterns first

    def replace_root(self, *roots):
        """Replace the existing root(s) with one or more new paths."""

        self._roots = []
        self.add_root(*roots)

    def add_handler(self, *handlers):
        """Add one or more handlers to this PdsLogger at the current location in the
        hierarchy.
        """

        if not self._logger:                # if logger is EasyLogger or NullLogger
            if handlers and not hasattr(self, 'warned'):
                raise ValueError(f'Class {type(self).__name__} does not accept handlers')
                warnings.warn(f'Class {type(self).__name__} does not accept handlers')
                self.warned = True
            return

        # Get list of full paths to the log files across all tiers
        log_files = [handler.baseFilename for handler in self._handlers
                     if isinstance(handler, logging.FileHandler)]

        # Add each new handler if its filename is unique
        for handler in handlers:
            if handler in self._handlers:
                continue
            if (isinstance(handler, logging.FileHandler) and
                    handler.baseFilename in log_files):
                continue

            self._local_handlers[-1].append(handler)
            self._handlers.append(handler)
            self._logger.addHandler(handler)

    def remove_handler(self, *handlers):
        """Remove one or more handlers from this PdsLogger."""

        if not self._logger:                # if logger is EasyLogger or NullLogger
            return

        for handler in handlers:
            if handler not in self._handlers:
                continue

            self._logger.removeHandler(handler)         # no exception if not present
            self._handlers.remove(handler)
            for handler_list in self._local_handlers:
                if handler in handler_list:
                    handler_list.remove(handler)
                    break

    def remove_all_handlers(self):
        """Remove all the handlers from this PdsLogger."""

        if not self._logger:                # if logger is EasyLogger or NullLogger
            return

        for handler in self._handlers:
            self._logger.removeHandler(handler)         # no exception if not present

        self._handlers = []
        self._local_handlers = [[] for _ in self._local_handlers]

    def replace_handler(self, *handlers):
        """Replace the existing handlers with one or more new global handlers."""

        self.remove_all_handlers()
        self.add_handler(handlers)

        # Move the new handlers to the top level
        if len(self._handlers) > 1:
            self._handlers[0] = self._handlers[-1]
            self._handlers[-1] = []

    ######################################################################################
    # logger.Logging API support
    ######################################################################################

    @staticmethod
    def getLogger(*args, **kwargs):
        return PdsLogger.get_logger(*args, **kwargs)

    @property
    def name(self):
        return self._logname

    @property
    def level(self):
        return self._logger.level

    @property
    def parent(self):
        return self._logger.parent

    @property
    def propagate(self):
        return self._logger.propagate

    @property
    def handlers(self):
        return self._handlers

    @property
    def disabled(self):
        return self._logger.disabled

    def setLevel(self, level):
        self.set_level(level)

    def isEnabledFor(self, level):
        return self._logger.isEnabledFor(level)

    def getEffectiveLevel(self):
        return self._logger.getEffectiveLevel()

    def getChild(self, suffix):
        name = self._logname + '.' + suffix
        if name in _LOOKUP:
            return _LOOKUP[name]
        return self._logger.getChild(suffix)

    def getChildren(self):
        loggers = self._logger.getChildren()
        loggers = {_LOOKUP.get(logger_.name, logger_) for logger_ in loggers}
            # Convert each logger to a PdsLogger if it's defined
        return loggers

    def addHandler(self, handler):
        self.add_handler(handler)

    def removeHandler(self, handler):
        self.remove_handler(handler)

    def hasHandlers(self):
        return bool(self._handlers)

    ######################################################################################
    # Logging methods
    ######################################################################################

    class _Closer():
        def __init__(self, logger):
            self.logger = logger

        def __enter__(self):
            pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.logger.close()

    def open(self, title, filepath='', *, level=None, limits={}, handler=[], force=False):
        """Begin a new tier in the logging hierarchy.

        Parameters:
            title (str):
                Title of the new section of the log.
            filepath (str, optional):
                Optional file path to include in the title.
            level (int, or str, optional):
                The level or level name for the minimum logging level to use within this
                tier. The default is to preserve the current logging level.
            limits (dict, optional):
                A dictionary mapping level name to the maximum number of messages of that
                level to include. Subsequent messages are suppressed. Use a limit of -1 to
                show all messages.
            handler (Handler or list[Handler], optional):
                Optional handler(s) to use only until this part of the logger is closed.

        Returns:
            context manager:
                A context manager enabling "`open logger.open():`" syntax. If `open()` is
                not being used as a context manager, this object can be ignored.
        """

        title = str(title)
        if filepath:
            title += ': ' + self._logged_filepath(filepath)

        new_level = level or self._min_levels[-1]

        # Write header message at current tier
        header_level = self._level_by_name['header']
        if header_level >= min(new_level, self._min_levels[-1]) or force:
            self._logger_log(header_level, self._logged_text('HEADER', title))

        # Increment the hierarchy depth
        if self._get_depth() >= self._maxdepth:
            raise ValueError('Maximum logging hierarchy depth has been reached')

        self._titles.append(title)
        self._start_times.append(datetime.datetime.now())

        # Update the handlers
        self._local_handlers.append([])
        handlers = handler if isinstance(handler, (list, tuple)) else [handler]
        self.add_handler(*handlers)

        # Set the level-specific limits
        self._limits_by_name.append(self._limits_by_name[-1].copy())
        for name, limit in limits.items():
            self._limits_by_name[-1][name] = limit

        # Unless overridden, each tier is bound by the limits of the tier above
        for name, limit in self._limits_by_name[-1].items():
            if name not in limits and limit >= 0:
                new_limit = max(0, limit - self._counters_by_name[-1][name])
                self._limits_by_name[-1][name] = new_limit

        # Create new message counters for this tier
        self._counters_by_name.append(defaultdict(int))
        self._suppressed_by_name.append(defaultdict(int))

        # Update the logging level
        self._min_levels.append(new_level)
        self.set_level(new_level)

        # For use of open() as a context manager
        return PdsLogger._Closer(self)

    def summarize(self):
        """Return a tuple describing the number of logged messages by category in the
        current tier of the hierarchy.

        Returns:
            tuple: (number of fatal errors, number of errors, number of warnings, total
            number of messages). These counts include messages that were
            suppressed because a limit was reached.
        """

        fatal = 0
        errors = 0
        warnings = 0
        total = 0
        for name, count in self._counters_by_name[-1].items():
            level = self._level_by_name[name]
            count += self._suppressed_by_name[-1][name]
            if level >= FATAL:
                fatal += count
            elif level >= ERROR:
                errors += count
            elif level >= WARNING:
                warnings += count

            total += count

        return (fatal, errors, warnings, total)

    def close(self, force=False):
        """Close the log at its current hierarchy depth, returning to the previous tier.

        The closure is logged, plus a summary of the time elapsed and levels identified
        while this tier was open.

        Parameters:
            force (bool, int, or str, optional):
                True to force the logging of all summary messages. Alternatively use a
                level or level name to force the summary messages only about logged
                messages at this level and higher.

        Returns:
            tuple: (number of fatal errors, number of errors, number of warnings, total
            number of messages). These counts include messages that were suppressed
            because a limit was reached.
        """

        # Interpret the `force` input
        if isinstance(force, str):
            min_level_for_log = self._level_by_name[_repair_level_name(force)]
        elif isinstance(force, bool):
            min_level_for_log = HIDDEN + 1 if force else min(self._min_levels[-2:])
        else:
            min_level_for_log = force

        # Create a list of messages summarizing results; each item is (logged level, text)
        header_level = self._level_by_name['header']
        messages = [(header_level, 'Completed: ' + self._titles[-1])]

        if self._timestamps:
            elapsed = datetime.datetime.now() - self._start_times[-1]
            messages += [(header_level, 'Elapsed time = ' + str(elapsed))]

        # Define messages indicating counts by level name
        tuples = [(level, name) for name, level in self._level_by_name.items()]
        tuples.sort(reverse=True)
        for level, name in tuples:
            count = self._counters_by_name[-1][name]
            suppressed = self._suppressed_by_name[-1][name]
            if count + suppressed == 0:
                continue

            capname = name.upper()
            if suppressed == 0:
                plural = '' if count == 1 else 's'
                note = f'{count} {capname} message{plural}'
            else:
                plural = '' if count == 1 else 's'
                note = (f'{count} {capname} message{plural} reported of '
                        f'{count + suppressed} total')

            messages += [(level, note)]

        # Transfer the totals to the hierarchy tier above
        if len(self._counters_by_name) > 1:
            for name, count in self._counters_by_name[-1].items():
                self._counters_by_name[-2][name] += count
                self._suppressed_by_name[-2][name] += self._suppressed_by_name[-1][name]

        # Determine values to return
        (fatal, errors, warnings, total) = self.summarize()

        # Close the handlers at this level
        for handler in self._local_handlers[-1]:
            if handler in self._handlers:
                self._handlers.remove(handler)
                self._logger.removeHandler(handler)

            # If the xattr module has been imported on a Mac, set the colors of the log
            # files to indicate outcome.
            if isinstance(handler, logging.FileHandler) and self._colors:
                try:                                                # pragma: no cover
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

        # Back up one level in the hierarchy
        self._titles             = self._titles[:-1]
        self._start_times        = self._start_times[:-1]
        self._limits_by_name     = self._limits_by_name[:-1]
        self._counters_by_name   = self._counters_by_name[:-1]
        self._suppressed_by_name = self._suppressed_by_name[:-1]
        self._local_handlers     = self._local_handlers[:-1]
        self._min_levels         = self._min_levels[:-1]

        if self._logger and self._min_levels:
            self._logger.setLevel(self._min_levels[-1])

        # Log the summary at the outer tier
        for level, note in messages:
            if level >= min_level_for_log:
                self._logger_log(header_level, self._logged_text('SUMMARY', note))

        # Blank line
        if self._blanklines:
            self.blankline(header_level)

        return (fatal, errors, warnings, total)

    def message_count(self, name):
        """Return the number of messages generated at this named level since this last
        open().

        Parameters:
            name (str): Name of a level.

        Returns:
            int: The number of messages logged, including any suppressed if a limit was
            reached.
        """

        name = _repair_level_name(name)
        return self._counters_by_name[-1][name] + self._suppressed_by_name[-1][name]

    def log(self, level, message, filepath='', *, force=False, suppress=False):
        """Log one record.

        Parameters:
            level (int or str):
                Logging level or level name.
            message (str):
                Message to log.
            filepath (str or pathlib.Path, optional):
                Path of the relevant file, if any.
            force (bool, optional):
                True to force message reporting even if the relevant limit has been
                reached or the level falls below this PdsLogger's minimum.
            suppress (bool, optional):
                True to suppress message reporting even if the relevant limit has not been
                reached. The message is still included in the count. The `force` option
                takes precedence over this option.
        """

        # Determine the level name and number
        if isinstance(level, str):
            level_name_for_log = _repair_level_name(level)
            level_name_for_count = level_name_for_log
            level_for_log = self._level_by_name[level_name_for_log]
        elif level in self._level_names:
            level_name_for_log = self._level_names[level]
            level_name_for_count = level_name_for_log
            level_for_log = level
        else:   # Level is not one of 10, 20, 30, etc.
            level_for_log = level
            level_name_for_log = self._logged_level_name(level)     # e.g., "ERROR+1"
            level_for_count = max(10*(level//10), HIDDEN)
            level_name_for_count = self._level_names[level_for_count]

        # Get the count and limit for messages with this level name
        count = self._counters_by_name[-1][level_name_for_count]
        limit = self._limits_by_name[-1].get(level_name_for_count, -1)

        # Determine whether to print
        if force:
            level_for_log = FATAL
            log_now = True
        elif suppress:
            log_now = False
        elif level_for_log < self._min_levels[-1]:
            log_now = False
        elif limit < 0:         # -1 means no limit
            log_now = True
        elif count >= limit:
            log_now = False
        else:
            log_now = True

        # Log now
        if log_now:
            text = self._logged_text(level_name_for_log, message, filepath)
            self._logger_log(level_for_log, text)
            self._counters_by_name[-1][level_name_for_count] += 1
            if not force:
                self._suppressions_logged.discard(level_name_for_count)

        # Otherwise...
        else:
            self._suppressed_by_name[-1][level_name_for_count] += 1

            # If this is the first suppressed message due to the limit, notify
            if (not suppress and limit >= 0
                    and level_for_log >= self._min_levels[-1]
                    and level_name_for_count not in self._suppressions_logged):
                message = f'Additional {level_name_for_count.upper()} messages suppressed'
                text = self._logged_text(level_name_for_count, message)
                self._logger_log(level_for_log, text)
                self._suppressions_logged.add(level_name_for_count)

    def debug(self, message, filepath='', force=False):
        """Log a message with level == "debug".

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "debug".
        """

        self.log('debug', message, filepath, force=force)

    def info(self, message, filepath='', force=False):
        """Log a message with level == "info".

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "info".
        """

        self.log('info', message, filepath, force=force)

    def warn(self, message, filepath='', force=False):
        """Log a message with level == "warn" or "warning".

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "warn".
        """

        self.log('warn', message, filepath, force=force)

    def error(self, message, filepath='', force=False):
        """Log a message with level == "error".

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "critical".
        """

        self.log('error', message, filepath, force=force)

    def critical(self, message, filepath='', force=False):
        """Log a message with level == "critical", equivalent to "fatal".

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "critical".
        """

        self.log('critical', message, filepath, force=force)

    def fatal(self, message, filepath='', force=False):
        """Log a message with level == "fatal".

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "fatal".
        """

        self.log('fatal', message, filepath, force=force)

    def normal(self, message, filepath='', force=False):
        """Log a message with level == "normal", equivalent to "info".

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "normal".
        """

        self.log('normal', message, filepath, force=force)

    def ds_store(self, message, filepath='', force=False):
        """Log a message with level == "ds_store", indicating that a file named
        ".DS_Store" was found.

        These files are sometimes created on a Mac.

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "ds_store".
        """

        self.log('ds_store', message, filepath, force=force)

    def dot_underscore(self, message, filepath='', force=False):
        """Log a message with level == `"dot_"`, indicating that a file with a name
        beginning with "._" was found.

        These files are sometimes created during file transfers from a Mac.

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of `"dot_"`.
        """

        self.log('dot_', message, filepath, force=force)

    def invisible(self, message, filepath='', force=False):
        """Log a message with level == "invisible", indicating that an invisible file was
        found.

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "invisible".
        """

        self.log('invisible', message, filepath, force=force)

    def hidden(self, message, filepath='', force=False):
        """Log a message with level == "hidden".

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "hidden".
        """

        self.log('hidden', message, filepath, force=force)

    def exception(self, error, filepath='', *, stacktrace=True):
        """Log an Exception or KeyboardInterrupt.

        This method is only to be used inside an "except" clause.

        Parameters:
            error (Exception): The error raised.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            stacktrace (bool, optional): True to include the stacktrace of the exception.

        Note:
            After a KeyboardInterrupt, this exception is re-raised.
        """

        if isinstance(error, KeyboardInterrupt):    # pragma: no cover (can't simulate)
            self.fatal('**** Interrupted by user')
            raise error

        if isinstance(error, LoggerError):
            filepath = error.filepath or filepath
            self.log(error.level, error.message, filepath, force=error.force)
            return

        (etype, value, tb) = sys.exc_info()
        if etype is None:                           # pragma: no cover (can't simulate)
            return      # Exception was already handled

        self.log('exception', '**** ' + etype.__name__ + ' ' + str(value),
                 filepath, force=True)

        if stacktrace:
            self._logger_log(self._level_by_name['exception'],
                             ''.join(traceback.format_tb(tb)))

    def blankline(self, level):
        self._logger_log(level, '')

    def _logger_log(self, level, message):
        """Log a message if it exceeds the logging level or is forced.

        Parameters:
            level (int): Logging level.
            message (str): Complete message text.
        """

        if not self._logger.handlers:       # if no handlers, print
            print(message)
        else:
            self._logger.log(level, message)

    ######################################################################################
    # Message formatting utilities
    ######################################################################################

    def _logged_text(self, level, message, filepath=''):
        """Construct a record to send to the logger, including time tag, level indicator,
        etc., in the standardized format.

        Parameters:
            level (int, str): Logging level or level name to appear in the log record.
            message (str): Message text.
            filepath (str or pathlib.Path, optional): File path to append to the message.

        Returns:
            str: The full text of the log message.
        """

        parts = []
        if self._timestamps:
            timetag = datetime.datetime.now().strftime(_TIME_FMT)
            if self._digits <= 0:
                timetag = timetag[:19]
            else:
                timetag = timetag[:20+self._digits]
            parts += [timetag, ' | ']

        if self._lognames:
            parts += [self._logname, ' | ']

        if self._pid:
            parts += [str(self._pid), ' | ']

        if self._indent:
            if parts:
                parts[-1] = ' |'
            parts += [self._get_depth() * '-', '| ']

        parts += [self._logged_level_name(level), ' | ', message]

        filepath = self._logged_filepath(filepath)
        if filepath:
            parts += [': ', str(filepath)]

        return ''.join(parts)

    def _logged_filepath(self, filepath=''):
        """A file path to log, with any of the leading root paths stripped.

        Parameters:
            filepath (str or pathlib.Path, optional): File path to append to the message.

        Returns:
            str: Path string to include in the logged message.
        """

        if isinstance(filepath, pathlib.Path):
            filepath = str(filepath)
            if filepath == '.':     # the result of Path('')
                filepath = ''

        if not filepath:
            return ''

        abspath = str(pathlib.Path(filepath).resolve())
        for root_ in self._roots:
            if filepath.startswith(root_):
                return filepath[len(root_):]
            if abspath.startswith(root_):
                return abspath[len(root_):]

        return filepath

    def _logged_level_name(self, level):
        """The name for a level to appear in the log, always upper case.

        Parameters:
            level (int, str): Logging level or level name.

        Returns:
            str: Level name to appear in the log.
        """

        if isinstance(level, str):
            return _repair_level_name(level).upper()

        level_name = self._level_names.get(level, '')
        if level_name:
            return level_name.upper()

        # Use "<name>+i" where i is the smallest difference above a default name
        diffs = [(level-lev, name.upper()) for lev, name in _DEFAULT_LEVEL_NAMES.items()]
        diffs = [diff for diff in diffs if diff[0] > 0]
        diffs.sort()
        return f'{diffs[0][1]}+{diffs[0][0]}'

    def _get_depth(self):
        """The current tier number (0-5) in the hierarchy."""

        return len(self._titles) - 1

##########################################################################################
# Alternative loggers
##########################################################################################

class EasyLogger(PdsLogger):
    """Simple subclass of PdsLogger that prints messages to the terminal."""

    _LOGGER_IS_FAKE = True      # Prevent registration as an actual logger

    def __init__(self, logname='easylog', **kwargs):
        PdsLogger.__init__(self, logname, **kwargs)

    def _logger_log(self, level, message):
        """Log a message if it exceeds the logging level or is forced.

        Parameters:
            level (int): Logging level.
            message (str): Complete message text.
        """

        print(message)


class NullLogger(EasyLogger):
    """Simple subclass of PdsLogger that suppresses all messages at except FATAL messages
    and those that have been forced.
    """

    def _logger_log(self, level, message):
        if level >= FATAL:
            print(message)

##########################################################################################

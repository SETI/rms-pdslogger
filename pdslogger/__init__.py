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

_DEFAULT_LEVEL_BY_NAME = {
    # Standard level values
    'fatal'   : logging.FATAL,  # 50
    'critical': logging.FATAL,  # 50
    'error'   : logging.ERROR,  # 40
    'warn'    : logging.WARN,   # 30
    'warning' : logging.WARN,   # 30
    'info'    : logging.INFO,   # 20
    'debug'   : logging.DEBUG,  # 10
    'hidden'  : HIDDEN,         #  1

    # Additional level values defined for every PdsLogger
    'normal'    : logging.INFO,
    'ds_store'  : logging.DEBUG,
    'dot_'      : logging.ERROR,
    'invisible' : logging.WARN,
    'exception' : logging.FATAL,
    'header'    : logging.INFO,
}

_DEFAULT_LEVEL_NAMES = {
    logging.FATAL: 'FATAL',     # 50
    logging.ERROR: 'ERROR',     # 40
    logging.WARN : 'WARNING',   # 30
    logging.INFO : 'INFO',      # 20
    logging.DEBUG: 'DEBUG',     # 10
    HIDDEN       : 'HIDDEN',    #  1
}

_DEFAULT_LIMITS_BY_NAME = {     # treating all as unlimited by default now
}

# Cache of names vs. PdsLoggers
_LOOKUP = {}

##########################################################################################
# Handlers
##########################################################################################

STDOUT_HANDLER = logging.StreamHandler(sys.stdout)
STDOUT_HANDLER.setLevel(HIDDEN + 1)


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
        level = _DEFAULT_LEVEL_BY_NAME[level.lower()]

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

    * "normal" is used for any normal outcome.
    * "ds_store" is to be used if a ".DS_Store" file is encountered.
    * "dot_" is to be used if a "._*" file is encountered.
    * "invisible" is to be used if any other invisible file or directory is encountered.
    * "exception" is to be used when any exception is encountered.
    * "header" is used for headers at the beginning of tests and for trailers at the ends
      of tests.

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
    logger having its own new limits and, optionally, its own handlers. Using this
    capability, a program that performs multiple tasks can generate one global log and
    also a separate log for each task. Each call to open() writes a section header into
    the log and each call to close() inserts a tally of messages printed at that and
    deeper tiers of the hierarchy.

    BY default, each log record automatically includes a time tag, log name, level, and a
    text message. The text message can be in two parts, typically a brief description
    followed by a file path. Optionally, the process ID can also be included. Options are
    provided to control which of these components are included.

    In the Macintosh Finder, log files are color-coded by the most severe message
    encountered within the file: green for info, yellow for warnings, red for errors, and
    violet for fatal errors.
    """

    _LOGGER_IS_FAKE = False     # Used by EasyLogger below

    def __init__(self, logname, *, default_prefix='pds.', levels={}, limits={}, roots=[],
                 timestamps=True, digits=6, lognames=True, pid=False, indent=True,
                 blanklines=True, colors=True, maxdepth=6, level=HIDDEN+1, ):
        """Constructor for a PdsLogger.

        Parameters:
            logname (str):
                Name of the logger. Each name for a logger must be globally unique.
            default_prefix (str, optional)
                The prefix to prepend to the logname if it is not already present. By
                default it is "pds.".
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
            level (int or str, optional):
                The minimum level of level name for a record to enter the log.
        """

        if default_prefix:
            default_prefix = default_prefix.rstrip('.') + '.'   # exactly one trailing dot
            if not logname.startswith(default_prefix):
                logname = default_prefix + logname

        parts = logname.split('.')
        if len(parts) not in (2, 3):
            raise ValueError('Log names must be of the form [pds.]xxx or [pds.]xxx.yyy')

        self._logname = logname
        if self._LOGGER_IS_FAKE:
            self._logger = None
        else:
            if logname in _LOOKUP:                                  # pragma: no cover
                raise ValueError(f'PdsLogger {self._logname} already exists')
            _LOOKUP[self._logname] = self           # Save logger in cache
            self._logger = logging.getLogger(self._logname)

        if isinstance(roots, str):
            roots = [roots]
        self._roots = []
        self.add_root(*roots)

        # Merge the dictionary of levels and their names
        self._level_by_name = _DEFAULT_LEVEL_BY_NAME.copy()     # name -> level
        for level_name, level_num in levels.items():
            if isinstance(level_num, str):
                level_num = _DEFAULT_LEVEL_BY_NAME[level_num.lower()]
            self._level_by_name[level_name] = level_num

        self._level_names = _DEFAULT_LEVEL_NAMES.copy()         # level -> primary name
        for level_name, level_num in self._level_by_name.items():
            if level_num not in self._level_names:
                self._level_names[level_num] = level_name

        # Support for multiple tiers in hierarchy
        self._titles              = [self._logname]
        self._start_times         = [datetime.datetime.now()]
        self._counters_by_name    = [defaultdict(int)]
        self._suppressed_by_name  = [defaultdict(int)]
        self._counters_by_level   = [defaultdict(int)]
        self._suppressed_by_level = [defaultdict(int)]
        self._local_handlers      = [[]]    # handlers at this tier but not above

        self._handlers = []     # complete list of handlers across all tiers

        # Merge the dictionary of limits
        limits_by_name = _DEFAULT_LIMITS_BY_NAME.copy()
        for level_name, level_num in self._level_by_name.items():
            limits_by_name.get(level_name, -1)
        for level_name, level_num in limits.items():
            limits_by_name[level_name] = level_num
        self._limits_by_name = [limits_by_name]

        # Log record format info
        self._timestamps = timestamps
        self._digits = digits
        self._lognames = lognames
        self._pid = os.getpid() if pid else 0
        self._indent = indent
        self._blanklines = blanklines
        self._colors = colors
        self._maxdepth = maxdepth
        self.set_level(level)

    def set_level(self, level):
        """Set the level of messages for this logger.

        Parameters;
            level (int or str, optional):
                The minimum level of level name for a record to enter the log.
        """

        if isinstance(level, str):
            self._min_level = self._level_by_name[level.lower()]
        else:
            self._min_level = level

        if self._logger:
            self._logger.setLevel(self._min_level)

    def add_root(self, *roots):
        """Add one or more paths to the root path."""

        for root_ in roots:
            root_ = str(root_).rstrip('/') + '/'
            if root_ not in self._roots:
                self._roots.append(root_)

        self._roots.sort(key=lambda x: (-len(x), x))    # longest patterns first

    def replace_root(self, *roots):
        """Replace the existing root(s) with one or more new paths."""

        self._roots = []
        self.add_root(*roots)

    def set_limit(self, name, limit):
        """Set upper limit on the number of messages with this level name.

        A limit of -1 implies no limit.
        """

        self._limits_by_name[-1][name.lower()] = limit

    def add_handler(self, *handlers):
        """Add one or more handlers to this PdsLogger at the current location in the
        hierarchy.
        """

        if not self._logger:    # if logger is "fake"
            return

        for handler in handlers:
            if handler in self._handlers:
                continue

            self._logger.addHandler(handler)
            self._handlers.append(handler)
            self._local_handlers[-1].append(handler)

    def remove_handler(self, *handlers):
        """Remove one or more handlers from this PdsLogger."""

        if not self._logger:    # if logger is "fake"
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

        if not self._logger:    # if logger is "fake"
            return

        for handler in self._handlers:
            self._logger.removeHandler(handler)         # no exception if not present

        self._handlers = []
        self._local_handlers = [[] for _ in self._local_handlers]

    def replace_handler(self, *handlers):
        """Replace the existing handlers with one or more new global handlers."""

        self.remove_all_handlers()
        for handler in handlers:
            if handler in self._handlers:
                continue

            self._logger.addHandler(handler)
            self._handlers.append(handler)
            self._local_handlers[0].append(handler)     # install as global

    @staticmethod
    def get_logger(logname):
        """The PdsLogger associated with the given name."""

        try:
            return _LOOKUP['pds.' + logname]
        except KeyError:
            return _LOOKUP[logname]

    ######################################################################################
    # logger.Logging API support
    ######################################################################################

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

    def open(self, title, filepath='', *, limits={}, handler=[], force=False):
        """Begin a new set of tests at a new tier in the hierarchy.

        Parameters:
            title (str):
                Title of the new section of the log.
            filepath (str, optional):
                Optional file path to include in the title.
            limits (dict, optional):
                A dictionary mapping level name to the maximum number of messages of that
                level to include. Subsequent messages are suppressed. Use a limit of -1 to
                show all messages.
            handler (Handler or list[Handler], optional):
                Optional handler(s) to use only until this part of the logger is closed.
            force (bool, optional):
                True to force the logging of this message even if the limit has been
                reached.
        """

        if filepath:
            title += ': ' + self._logged_filepath(filepath)

        # Write header message at current level
        level = self._level_by_name['header']
        self._logger_log(level, self._logged_text('HEADER', title), force=force)

        # Increment the hierarchy depth
        if self._get_depth() >= self._maxdepth:
            raise ValueError('Maximum logging hierarchy depth has been reached')

        self._titles.append(title)
        self._start_times.append(datetime.datetime.now())

        # Save any level-specific handlers if necessary
        self._local_handlers.append([])
        if isinstance(handler, (list, tuple)):
            handlers = handler
        else:
            handlers = [handler]

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

            self._logger.addHandler(handler)
            self._local_handlers[-1].append(handler)
            self._handlers.append(handler)

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
        self._counters_by_level.append(defaultdict(int))
        self._suppressed_by_level.append(defaultdict(int))

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
        tests = 0
        for level, count in self._counters_by_level[-1].items():
            if level >= FATAL:
                fatal += count
            elif level >= ERROR:
                errors += count
            elif level >= WARNING:
                warnings += count

            tests += count

        return (fatal, errors, warnings, tests)

    def close(self):
        """Close the log at its current hierarchy depth, returning to the previous tier.

        The closure is logged, plus an accounting of the time elapsed and levels
        identified while this tier was open.

        Returns:
            tuple: (number of fatal errors, number of errors, number of warnings, total
                    number of messages). These counts include messages that were
                    suppressed because a limit was reached.
        """

        # Create a list of messages summarizing results; each item is (level, text)
        header = self._level_by_name['header']
        messages = [(header, 'Completed: ' + self._titles[-1])]

        if self._timestamps:
            elapsed = datetime.datetime.now() - self._start_times[-1]
            messages += [(header, 'Elapsed time = ' + str(elapsed))]

        # Include messages indicating counts by level name
        tuples = [(level, name) for name, level in self._counters_by_name[-1].items()]
        tuples.sort()
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
                unsuppressed = count - suppressed
                plural = '' if unsuppressed == 1 else 's'
                note = (f'{unsuppressed} {capname} message{plural} reported of '
                        f'{count} total')

            messages += [(max(level, header), note)]

        # Transfer the totals to the hierarchy depth above
        if len(self._counters_by_name) > 1:
            for name, count in self._counters_by_name[-1].items():
                self._counters_by_name[-2][name] += count
                self._suppressed_by_name[-2][name] += self._suppressed_by_name[-1][name]

            for level, count in self._counters_by_level[-1].items():
                self._counters_by_level[-2][level] += count
                self._suppressed_by_level[-2][level] += \
                                                self._suppressed_by_level[-1][level]

        # Determine values to return
        (fatal, errors, warnings, tests) = self.summarize()

        # Close the handlers this level
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
        self._titles              = self._titles[:-1]
        self._start_times         = self._start_times[:-1]
        self._limits_by_name      = self._limits_by_name[:-1]
        self._counters_by_name    = self._counters_by_name[:-1]
        self._suppressed_by_name  = self._suppressed_by_name[:-1]
        self._counters_by_level   = self._counters_by_level[:-1]
        self._suppressed_by_level = self._suppressed_by_level[:-1]
        self._local_handlers      = self._local_handlers[:-1]

        # Log the summary at the higher depth
        for level, note in messages:
            message = self._logged_text('summary', note)
            self._logger_log(level, message)

        # Blank line
        if self._blanklines:
            self.blankline(header)

        return (fatal, errors, warnings, tests)

    def log(self, level, message, filepath='', *, force=False):
        """Log one record.

        Parameters:
            level (int or str): logging level or level name.
            message (str): message to log.
            filepath (str or pathlib.Path, optional): Path of the relevant file, if any.
            force (bool, optional): True to force message reporting even if the relevant
                limit has been reached.
        """

        # Determine the level
        if isinstance(level, str):
            level_name = level.lower()
            level = self._level_by_name[level_name]
        elif level in self._level_names:
            level_name = self._level_names[level]
        else:   # Level is not one of 10, 20, 30, etc.
            level_name = ''

        # Count the messages at this level
        if level_name:
            self._counters_by_name[-1][level_name] += 1
        if level in self._counters_by_level[-1]:
            key = level
        else:
            key = max(10 * (level//10), HIDDEN)
        self._counters_by_level[-1][key] += 1

        # Log message if necessary
        limit = self._limits_by_name[-1].get(level_name, -1)
        if limit < 0 or self._counters_by_name[-1][level_name] <= limit:
            log_now = True
        else:
            log_now = force

        if log_now:
            text = self._logged_text(level_name or level, message, filepath)
            self._logger_log(level, text, force=force)

        # Otherwise, count suppressed messages
        else:
            self._suppressed_by_name[-1][level_name] += 1
            self._suppressed_by_level[-1][level] += 1

            # Note first suppression
            if self._suppressed_by_name[-1][level_name] == 1 and limit != 0:
                level_id = self._level_names.get(level, str(level))
                if level_name.upper() == level_id:
                    type_ = level_id
                else:
                    type_ = level_name + ' ' + level_id

                message = f'Additional {type_} messages suppressed'
                text = self._logged_text(level_name, message)
                self._logger_log(level, text)

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
        """Log a message with level == "dot_", indicating that a file with a name
        beginning with "._" was found.

        These files are sometimes created during file transfers from a Mac.

        Parameters:
            message (str): Text of the message.
            filepath (str or pathlib.Path, optional): File path to include in the message.
            force (bool, optional): True to force the message to be logged even if the
                logging level is above the level of "dot_".
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

    def _logger_log(self, level, message, force=False):
        level = FATAL if force else level
        if level >= self._min_level:
            if self._logger and not self._logger.handlers:  # if no handlers, print
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

        parts += [self._logged_level(level), ' | ', message]

        filepath = self._logged_filepath(filepath)
        if filepath:
            parts += [': ', filepath]

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

    def _logged_level(self, level):
        """The name for a level to appear in the log, always upper case.

        Parameters:
            level (int, str): Logging level or level name.

        Returns:
            str: Level name to appear in the log.
        """

        if isinstance(level, str):
            return level.upper()

        level_name = self._level_names.get(level, '')
        if level_name:
            return level_name.upper()

        # Use "<name>+i" where i is the smallest difference above a default name
        diffs = [(level-lev, name) for lev, name in _DEFAULT_LEVEL_NAMES.items()]
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
    """Simple subclass of PdsLogger that prints all messages at or above a specified level
    to the terminal.
    """

    _LOGGER_IS_FAKE = True      # Prevent registration as an actual logger

    def __init__(self, logname='easylog', *, default_prefix='pds.', levels={}, limits={},
                 roots=[], timestamps=True, digits=6, lognames=True, pid=False,
                 indent=True, blanklines=True, colors=True, maxdepth=6, level=HIDDEN+1):
        """Constructor for an EasyLogger.

        Parameters:
            logname (str):
                Name of the logger. Each name for a logger must be globally unique.
            default_prefix (str, optional)
                The prefix to prepend to the logname if it is not already present. By
                default it is "pds.".
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
            level (int or str, optional):
                The minimum level of level name for a record to enter the log.
        """

        global _LOOKUP

        # Override the test regarding whether this logger already exists
        saved_lookup = _LOOKUP.copy()
        _LOOKUP.clear()
        try:
            PdsLogger.__init__(self, logname, default_prefix=default_prefix,
                               levels=levels, limits=limits, roots=roots,
                               timestamps=timestamps, digits=digits, lognames=lognames,
                               pid=pid, indent=indent, blanklines=blanklines,
                               colors=colors, maxdepth=maxdepth, level=level)
        finally:
            for key, value in saved_lookup.items():
                _LOOKUP[key] = value

        self.set_level(level)

    def _logger_log(self, level, message, *, force=False):
        if isinstance(level, str):
            level = self._level_by_name[level.lower()]
        if level >= self._min_level or force:
            print(message)


class NullLogger(EasyLogger):
    """Supports the full PdsLogger interface but generally does no logging.

    Messages are only printed when the level is FATAL or when `force` is True.
    """

    def _logger_log(self, level, message, *, force=False):
        if force or level >= FATAL:
            print(message)

##########################################################################################

[![GitHub release; latest by date](https://img.shields.io/github/v/release/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/releases)
[![GitHub Release Date](https://img.shields.io/github/release-date/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/releases)
[![Test Status](https://img.shields.io/github/actions/workflow/status/SETI/rms-pdslogger/run-tests.yml?branch=main)](https://github.com/SETI/rms-pdslogger/actions)
[![Documentation Status](https://readthedocs.org/projects/rms-pdslogger/badge/?version=latest)](https://rms-pdslogger.readthedocs.io/en/latest/?badge=latest)
[![Code coverage](https://img.shields.io/codecov/c/github/SETI/rms-pdslogger/main?logo=codecov)](https://codecov.io/gh/SETI/rms-pdslogger)
<br />
[![PyPI - Version](https://img.shields.io/pypi/v/rms-pdslogger)](https://pypi.org/project/rms-pdslogger)
[![PyPI - Format](https://img.shields.io/pypi/format/rms-pdslogger)](https://pypi.org/project/rms-pdslogger)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/rms-pdslogger)](https://pypi.org/project/rms-pdslogger)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/rms-pdslogger)](https://pypi.org/project/rms-pdslogger)
<br />
[![GitHub commits since latest release](https://img.shields.io/github/commits-since/SETI/rms-pdslogger/latest)](https://github.com/SETI/rms-pdslogger/commits/main/)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/commits/main/)
[![GitHub last commit](https://img.shields.io/github/last-commit/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/commits/main/)
<br />
[![Number of GitHub open issues](https://img.shields.io/github/issues-raw/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/issues)
[![Number of GitHub closed issues](https://img.shields.io/github/issues-closed-raw/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/issues)
[![Number of GitHub open pull requests](https://img.shields.io/github/issues-pr-raw/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/pulls)
[![Number of GitHub closed pull requests](https://img.shields.io/github/issues-pr-closed-raw/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/pulls)
<br />
![GitHub License](https://img.shields.io/github/license/SETI/rms-pdslogger)
[![Number of GitHub stars](https://img.shields.io/github/stars/SETI/rms-pdslogger)](https://github.com/SETI/rms-pdslogger/stargazers)
![GitHub forks](https://img.shields.io/github/forks/SETI/rms-pdslogger)

# Introduction

`pdslogger` provides a new class and associated functions that augment the functionality
of the standard Python `logging` module.

`pdslogger` is a product of the [PDS Ring-Moon Systems Node](https://pds-rings.seti.org).

# Installation

The `pdslogger` module is available via the `rms-pdslogger` package on PyPI and can be
installed with:

```sh
pip install rms-pdslogger
```

# Getting Started

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

Details of each function and class are available in the [module
documentation](https://rms-pdslogger.readthedocs.io/en/latest/module.html).

This simple example:

```python
import pdslogger
logger = pdslogger.PdsLogger('sample', default_prefix='test')
logger.warn('Warning message')
with logger.open('Sub-log'):
    logger.debug('Debug message level 2')
logger.close()
```

will yield:

```
2024-12-04 13:47:37.004203 | test.sample || WARNING | Warning message
2024-12-04 13:47:37.004224 | test.sample || HEADER | Sub-log
2024-12-04 13:47:37.004240 | test.sample |-| DEBUG | Debug message level 2
2024-12-04 13:47:37.004270 | test.sample || SUMMARY | Completed: Sub-log
2024-12-04 13:47:37.004276 | test.sample || SUMMARY | Elapsed time = 0:00:00.000016
2024-12-04 13:47:37.004280 | test.sample || SUMMARY | 1 DEBUG message

2024-12-04 13:47:37.004295 | test.sample || SUMMARY | Completed: test.sample
2024-12-04 13:47:37.004299 | test.sample || SUMMARY | Elapsed time = 0:00:00.000094
2024-12-04 13:47:37.004302 | test.sample || SUMMARY | 1 WARNING message
2024-12-04 13:47:37.004305 | test.sample || SUMMARY | 1 DEBUG message

```

# Contributing

Information on contributing to this package can be found in the
[Contributing Guide](https://github.com/SETI/rms-vax/blob/main/CONTRIBUTING.md).

# Links

- [Documentation](https://rms-vax.readthedocs.io)
- [Repository](https://github.com/SETI/rms-vax)
- [Issue tracker](https://github.com/SETI/rms-vax/issues)
- [PyPi](https://pypi.org/project/rms-vax)

# Licensing

This code is licensed under the [Apache License v2.0](https://github.com/SETI/rms-vax/blob/main/LICENSE).

#!/usr/bin/env python3
from __future__ import print_function, unicode_literals

import errno
import logging
import os
import re
import resource
import subprocess
import sys
import tempfile

PROGRAM = ['./msh']

# Notes on interpreting this test cases:
#
# The expected values for stdout and stderr are regular expressions, so
#   .* means any string (including empty strings)
#   .+ means any string (excluding empty strings)
# All pattern-matching is case-insensitive.
#
# If allow_extra_stdout or allow_extra_stderr is set in a test case, then
# extra lines of output can be given from stdout or stderr by the shell.
# Otherwise, no extra lines are allowed.
#
# Some test cases have an 'expect_output_files' argument, which is
# a list of files expected to be created by the test case and their contents.
# 
# Some test cases have a 'prepare_function' argument, whcih is some python code
# to run before running the test case.
# 
# Some test cases have a 'extra_popen' argument, which are extra flags to pass
# to subprocess.Popen

NON_PIPE_TESTS = [
    {
        'name': 'exit immediately',
        'input': ['exit'],
        'stdout': ['> '],
        'stderr': [],
    },
    {
        'name': 'trivial command, exit status 0',
        'input': ['/bin/true','exit'],
        'stdout': ['> .*/bin/true.*[Ee]xit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command, exit status 0 (do not check for command name)',
        'input': ['/bin/true','exit'],
        'stdout': ['> .*[Ee]xit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command with extra space, exit status 0',
        'input': [' /bin/true','exit'],
        'stdout': ['> .*/bin/true.*[Ee]xit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command with extra tab, exit status 0',
        'input': ['\t/bin/true','exit'],
        'stdout': ['> .*[Ee]xit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command with extra vertical tab, exit status 0',
        'input': ['\v/bin/true','exit'],
        'stdout': ['> .*[Ee]xit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command, exit status 1',
        'input': ['/bin/false','exit'],
        'stdout': ['> /bin/false.*[Ee]xit status: 1.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command, exit status 1 (do not check for command name)',
        'input': ['/bin/false','exit'],
        'stdout': ['> .*[Ee]xit status: 1.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command, exit status 2 (check for command name)',
        'input': ['test/exit2.sh','exit'],
        'stdout': ['> test/exit2.sh.*exit status: 2.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command, exit status 2 (do not check for command name)',
        'input': ['test/exit2.sh','exit'],
        'stdout': ['> .*exit status: 2.*', '> '],
        'stderr': [],
    },
    {
        'name': 'trivial command, exit status 1 (check for command name)',
        'input': ['/bin/false','exit'],
        'stdout': ['> /bin/false.*[Ee]xit status: 1.*', '> '],
        'stderr': [],
    },
    {
        'name': 'only redirections is invalid',
        'input': ['> foo.txt < bar.txt','exit'],
        'stdout': ['> > '],
        'stderr': ['.*invalid command.*'],
    },
    {
        'name': 'redirection to nothing is invalid',
        'input': ['/bin/true > ','exit'],
        'stdout': ['> > '],
        'stderr': ['.*invalid command.*'],
    },
    {
        'name': 'redirection from nothing is invalid',
        'input': ['/bin/true < ','exit'],
        'stdout': ['> > '],
        'stderr': ['.*invalid command.*'],
    },
    {
        'name': 'pass arguments',
        'input': ['test/argument_test.sh first second_with_underscore third', 'exit'],
        'stdout': [
            '> ',
            'number of arguments: 3',
            'argument 1: first',
            'argument 2: second_with_underscore',
            'argument 3: third',
            'argument 4: ',
            'test/argument_test.sh.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': '" is not quote',
        'input': ['test/argument_test.sh "not quoted"', 'exit'],
        'stdout': [
            '> ',
            'number of arguments: 2',
            'argument 1: "not',
            'argument 2: quoted"',
            'argument 3: ',
            'argument 4: ',
            'test/argument_test.sh.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': 'varying argument counts and lengths',
        'input': ['test/argument_test.sh aX bX cX dX eX', 'test/argument_test.sh f g hZZ i', 'test/argument_test.sh j k l',  'exit'],
        'stdout': [
            '> ',
            'number of arguments: 5',
            'argument 1: aX',
            'argument 2: bX',
            'argument 3: cX',
            'argument 4: dX',
            'test/argument_test.sh.*exit status: 0.*',
            '> ',
            'number of arguments: 4',
            'argument 1: f',
            'argument 2: g',
            'argument 3: hZZ',
            'argument 4: i',
            'test/argument_test.sh.*exit status: 0.*',
            '> ',
            'number of arguments: 3',
            'argument 1: j',
            'argument 2: k',
            'argument 3: l',
            'argument 4: ',
            'test/argument_test.sh.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': 'varying command lengths (1)',
        'input': ['./test/argument_test.sh a b c d e', '/bin/echo f g h i', 'test/argument_test.sh j k l',  'exit'],
        'stdout': [
            '> ',
            'number of arguments: 5',
            'argument 1: a',
            'argument 2: b',
            'argument 3: c',
            'argument 4: d',
            './test/argument_test.sh .*exit status: 0.*',
            '> f g h i',
            '/bin/echo.*exit status: 0.*',
            '> ',
            'number of arguments: 3',
            'argument 1: j',
            'argument 2: k',
            'argument 3: l',
            'argument 4: ',
            'test/argument_test.sh.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': 'varying command lengths (2)',
        'input': ['/bin/echo f g h i', './test/argument_test.sh aXX bXX cXX dXX eXX', 'test/argument_test.sh j k l',  'exit'],
        'stdout': [
            '> f g h i',
            '.*exit status: 0.*',
            '> ',
            'number of arguments: 5',
            'argument 1: aXX',
            'argument 2: bXX',
            'argument 3: cXX',
            'argument 4: dXX',
            '.*exit status: 0.*',
            '> ',
            'number of arguments: 3',
            'argument 1: j',
            'argument 2: k',
            'argument 3: l',
            'argument 4: ',
            '.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': 'very long argument',
        'input': ['/bin/echo short', '/bin/echo ' + ('Q' * 80),  'exit'],
        'stdout': [
            '> short',
            '.*exit status: 0.*',
            '> ' + ('Q' * 80),
            '.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': 'lots of arguments',
        'input': ['/bin/echo short', 'test/argument_test.sh ' + ' '.join(map(lambda i: chr(ord('A') + i), range(20))), 'exit'],
        'stdout': [
            '> short',
            '.*exit status: 0.*',
            '> ',
            'number of arguments: 20',
            'argument 1: A',
            'argument 2: B',
            'argument 3: C',
            'argument 4: D',
            '.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': 'extra whitespace without redirects',
        'input': ['   \t\t /bin/echo\ttesting    one   two \vthree ', 'exit'],
        'stdout': ['> testing one two three', '.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'redirections require whitespace around >',
        'input': ['/bin/echo  this is a >test', 'exit'],
        'stdout': ['> this is a >test', '.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'redirections require whitespace around <',
        'input': ['/bin/echo  this is a <test', 'exit'],
        'stdout': ['> this is a <test', '.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': '>> is not a redirection operator',
        'input': ['/bin/echo  this is a >> test', 'exit'],
        'stdout': ['> this is a >> test', '.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'redirect stdin inode',
        'input': ['/usr/bin/stat -L -c %i/%d /proc/self/fd/0 < test/input.txt', 'exit'],
        'stdout': [
            '> {}/{}'.format(
                os.stat('test/input.txt').st_ino,
                os.stat('test/input.txt').st_dev,
            ),
            '.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': 'redirect stdin contents',
        'input': ['/bin/cat < test/input.txt', 'exit'],
        'stdout': [
            '> This is an example input file.',
            'Which has multiple lines.',
            '.*exit status: 0.*',
            '> ',
        ],
        'stderr': [],
    },
    {
        'name': 'fork fails',
        'input': ['/bin/echo testing one two three', 'exit'],
        'stdout': ['> > '],
        'stderr': ['.+'], # some non-empty error message
        'allow_extra_stderr': True,
        'extra_popen': {
            'preexec_fn': lambda: resource.setrlimit(resource.RLIMIT_NPROC, (0,0)),
        },
    },
    {
        'name': 'exec fails',
        'input': ['test/invalid-exec', 'exit'],
        'stdout': [],
        'allow_extra_stdout': True,
        'stderr': ['.+'], # some non-empty error message
        'allow_extra_stderr': True,
    },
    {
        'name': 'redirect stdout',
        'input': ['/bin/echo testing one two three > test/redirect-stdout-output.txt', 'exit'],
        'expect_output_files': {
            'test/redirect-stdout-output.txt' : ['testing one two three']
        },
        'stdout': ['.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'redirect stdout does not redirect stderr',
        'input': ['test/sample_outputs.sh > test/redirect-stdout-output.txt', 'exit'],
        'expect_output_files': {
            'test/redirect-stdout-output.txt' : ['This is the contents of stdout.']
        },
        'stdout': ['.*exit status: 0.*', '> '],
        'stderr': ['This is the contents of stderr.'],
    },
    {
        'name': 'redirect in middle of command',
        'input': ['/bin/echo testing one two > test/redirect-stdout-output.txt three ', 'exit'],
        'expect_output_files': {
            'test/redirect-stdout-output.txt' : ['testing one two three']
        },
        'stdout': ['.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'redirect at beginning of command',
        'input': ['> test/redirect-stdout-output.txt /bin/echo testing one two three ', 'exit'],
        'expect_output_files': {
            'test/redirect-stdout-output.txt' : ['testing one two three']
        },
        'stdout': ['.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'extra whitespace in redirect at beginning',
        'input': ['  >    \ttest/redirect-stdout-output.txt\t  /bin/echo\ttesting    one   two \vthree ', 'exit'],
        'expect_output_files': {
            'test/redirect-stdout-output.txt' : ['testing one two three']
        },
        'stdout': ['.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'redirect output then use normal output',
        'input': ['/bin/echo foo > /dev/null', '/bin/echo bar', 'exit'],
        'stdout': ['> .*exit status: 0.*', '> bar', '.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': 'redirect input then use normal input',
        'input': ['/usr/bin/stat -L -c %F /proc/self/fd/0', '/bin/cat < test/input.txt', '/usr/bin/stat -L -c %F /proc/self/fd/0', 'exit'],
        'stdout': [
            '> fifo', '.*exit status: 0.*',
            '> This is an example input file.', 'Which has multiple lines.', '.*exit status: 0.*',
            '> fifo', '.*exit status: 0.*',
            '> '
        ],
        'stderr': [],
    },
    {
        'name': 'redirect output truncates file',
        'input': ['/bin/echo testing one two three > test/redirect-stdout-output.txt', 'exit'],
        'expect_output_files': {
            'test/redirect-stdout-output.txt' : ['testing one two three'],
        },
        'stdout': ['.*exit status: 0.*', '> '],
        'stderr': [],
        'prepare_function': lambda: create_file('test/redirect-stdout-output.txt',
            'This is a long string meant to ensure that echo\n'
            'will not overwrite it if the shell does not open\n'
            'the file with O_TRUNC.\n'
            'This is a long string meant to ensure that echo\n'
            'will not overwrite it if the shell does not open\n'
            'the file with O_TRUNC.\n'
        ),
    },
    {
        'name': 'echo 100 times output',
        'input': list(map(lambda i: '/bin/echo %s' % (i), range(100))) + ['exit'],
        'stdout': list(map(lambda i: '.*%s' % (i), range(100))), # .* for possible prefix of prompt
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'echo 100 times exit status',
        'input': list(map(lambda i: '/bin/echo %s' % (i), range(100))) + ['exit'],
        'stdout': list(map(lambda i: '.*exit status: 0.*', range(100))),
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': '100 output redirections (with limit of 50 open files)',
        'input': list(map(lambda i: '/bin/echo valuefrom%s > test/redirect-output-%s' % (i, i), range(100))) + ['exit'],
        'stdout': list(map(lambda i: '.*exit status: 0.*', range(100))),
        'stderr': [],
        'expect_output_files': dict(list(map(
            lambda i: ('test/redirect-output-%s' % (i), ['valuefrom%s' % (i)]),
            range(100)
        ))),
        'allow_extra_stdout': True,
        'extra_popen': {
            'preexec_fn': lambda: resource.setrlimit(resource.RLIMIT_NOFILE, (50,50)),
        },
    },  
    {
        'name': '100 input redirections (with limit of 50 open files)',
        'input': list(map(lambda i: '/bin/cat < test/input.txt', range(100))) + ['exit'],
        'stdout': list(map(lambda i: '.*This is an example input file.', range(100))),
        'stderr': [],
        'allow_extra_stdout': True,
        'extra_popen': {
            'preexec_fn': lambda: resource.setrlimit(resource.RLIMIT_NOFILE, (50,50)),
        },
    },
    {
        'name': 'redirect to operator is invalid',
        'input': ['/bin/false > > ', 'exit'],
        'stdout': ['> > '],
        'stderr': ['.*invalid command.*'],
    },
    {
        'name': 'non-existing command',
        'input': ['/bin/trex', 'exit'],
        'stdout': [],
        'stderr': ['.*(?:No such file or directory|Command not found).*'],
        'allow_extra_stdout': True,
        'allow_extra_stderr': True,
    },
    {
        'name': 'run example out and exit',
        'input': ['test/example_out.sh', 'exit'],
        'stdout': ['> foo bar baz'],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'run sample outputs and exit',
        'input': ['test/sample_outputs.sh', 'exit'],
        'stdout': ['> This is the contents of stdout.'],
        'stderr': ['This is the contents of stderr.'],
        'allow_extra_stdout': True,
    },
    {
        'name': 'run sample outputs, then example out, then sample outputs, then exit',
        'input': ['test/sample_outputs.sh', 'test/example_out.sh', 'test/sample_outputs.sh', 'exit'],
        'stdout': ['> This is the contents of stdout.',
                   '> foo bar baz',
                   '> This is the contents of stdout.',
                   '> ',
                ],
        'stderr': ['This is the contents of stderr.', 'This is the contents of stderr.'],
        'allow_extra_stdout': True,
    },
    {
        'name': 'run sample outputs, then example out, then sample outputs, then exit (no exit statues)',
        'input': ['test/sample_outputs.sh', 'test/example_out.sh', 'test/sample_outputs.sh', 'exit'],
        'stdout': ['> This is the contents of stdout.',
                   '> foo bar baz',
                   '> This is the contents of stdout.',
                   '> ',
                ],
        'stderr': ['This is the contents of stderr.', 'This is the contents of stderr.'],
        'allow_extra_stdout': True,
    },
    {
        'name': 'redirect stdin, then use other input (no arguments)',
        'input': ['/bin/cat < test/input.txt', 'test/statfd0.sh', 'exit'],
        'stdout': [
            '> This is an example input file.', 'Which has multiple lines.',
            '> fifo',
            '> '
        ],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'redirect output (no arguments)',
        'input': ['test/example_out.sh > test/redirect-stdout-output.txt', 'exit'],
        'stdout': [],
        'stderr': [],
        'expect_output_files': {
            'test/redirect-stdout-output.txt': ['foo bar baz']
        },
        'allow_extra_stdout': True,
    },
    {
        'name': 'redirect output then use normal output (no arguments)',
        'input': ['test/sample_outputs.sh > test/redirect-stdout-output.txt', 'test/example_out.sh', 'exit'],
        'stdout': ['.*foo bar baz'],
        'stderr': ['This is the contents of stderr.'],
        'expect_output_files': {
            'test/redirect-stdout-output.txt': ['This is the contents of stdout.']
        },
        'allow_extra_stdout': True,
    },
    {
        'name': 'redirect output truncates file (no arguments)',
        'input': ['test/example_out.sh > test/redirect-stdout-output.txt', 'exit'],
        'stdout': [],
        'stderr': [],
        'expect_output_files': {
            'test/redirect-stdout-output.txt': ['foo bar baz']
        },
        'prepare_function': lambda: create_file('test/redirect-stdout-output.txt',
            'This is a long string meant to ensure that echo\n'
            'will not overwrite it if the shell does not open\n'
            'the file with O_TRUNC.\n'
            'This is a long string meant to ensure that echo\n'
            'will not overwrite it if the shell does not open\n'
            'the file with O_TRUNC.\n'
        ),
        'allow_extra_stdout': True,
    },
]
PIPE_TESTS = [
    # pipe related tests
    {
        'name': 'pipe in the end without a command is invalid',
        'input': ['/bin/ls |', 'exit'],
        'stdout': ['> > '],
        'stderr': ['.*invalid command.*'],
        'allow_extra_stderr': True,
    },

    {
        'name': 'fork fails in a pipeline ',
        'input': ['/bin/cat | /bin/cat | /bin/cat | /bin/cat', 'exit'],
        'stdout': ['> > '],
        'stderr': ['.+'], # some non-empty error message
        'allow_extra_stderr': True,
        'extra_popen': {
            'preexec_fn': lambda: resource.setrlimit(resource.RLIMIT_NPROC, (0,0)),
        },
    },
    {
        'name': 'two command pipeline without arguments',
        'input': ['test/example_out.sh | test/example_sed.sh', 'exit'],
        'stdout': ['.*foo XXX baz'],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'two command pipeline without arguments, then use output',
        'input': ['test/example_out.sh | test/example_sed.sh', 'test/example_out.sh', 'exit'],
        'stdout': ['.*foo XXX baz', '.*foo bar baz'],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'two command pipeline without arguments twice',
        'input': ['test/example_out.sh | test/example_sed.sh', 'test/example_out.sh | test/example_sed2.sh', 'exit'],
        'stdout': ['.*foo XXX baz', '.*foo bar YYY'],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'three command pipeline without arguments (outputs)',
        'input': ['test/example_out.sh | test/example_sed2.sh | test/example_sed.sh', 'exit'],
        'stdout': ['.*foo XXX YYY'],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'three command pipeline without arguments (status codes)',
        'input': ['test/example_out.sh | test/example_sed2.sh | test/example_sed.sh', 'exit'],
        'stdout': [
            '.*test/example_out.sh.*exit status:.*0.*',
            '.*test/example_sed2.sh.*exit status:.*0.*',
            '.*test/example_sed.sh.*exit status:.*0.*',
        ],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'three command pipeline without arguments where order matters (1)',
        'input': ['test/example_out.sh | test/example_sed2.sh | test/example_sed3.sh', 'exit'],
        'stdout': ['.*foo bar ZZZ'],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': 'three command pipeline without arguments where order matters (2)',
        'input': ['test/example_out.sh | test/example_sed3.sh | test/example_sed2.sh', 'exit'],
        'stdout': ['.*foo bar YYY'],
        'stderr': [],
        'allow_extra_stdout': True,
    },
    {
        'name': '|s without spaces is not a pipeline',
        'input': ['/bin/echo this|argument|has|pipes', 'exit'],
        'stdout': [r'> this\|argument\|has\|pipes', '.*exit status: 0.*', '> '],
        'stderr': [],
    },
    {
        'name': '|s without spaces mixed with | with spaces (output)',
        'input': ['/bin/echo this|argument|has|pipes | /bin/sed -e s/argument/XXX/', 'exit'],
        'stdout': [r'.*this\|XXX\|has\|pipes', '> '],
        'allow_extra_stdout': True,
        'stderr': [],
    },
    {
        'name': '|s without spaces mixed with | with spaces (exit statuses)',
        'input': ['/bin/echo this|argument|has|pipes | /bin/sed -e s/argument/XXX/', 'exit'],
        'stdout': ['.*exit status: 0.*', '.*exit status: 0.*'],
        'allow_extra_stdout': True,
        'stderr': [],
    },
    {
        'name': 'simple pipe output',
        'input': ['/bin/echo testing  one two three | /bin/sed -e s/one/XXX/', 'exit'],
        'stdout': [
            '.*testing XXX two three',
        ],
        'allow_extra_stdout': True,
        'stderr': []
    },
    {
        'name': 'simple pipe exit status',
        'input': ['/bin/echo testing one two three | /bin/sed -e s/one/XXX/', 'exit'],
        'stdout': [
            '.*exit status: 0.*',
            '.*exit status: 0.*',
        ],
        'allow_extra_stdout': True,
        'stderr': []
    },
    {
        'name': 'longer pipeline (output)',
        'input': ['/bin/echo testing one two three | /bin/sed -e s/one/XXX/ | /bin/sed -e s/two/YYY/', 'exit'],
        'stdout': [
            '.*testing XXX YYY three',
        ],
        'allow_extra_stdout': True,
        'stderr': []
    },
    {
        'name': 'longer pipeline exit status (all 0s)',
        'input': ['/bin/echo testing one two three | /bin/sed -e s/one/XXX/ | /bin/sed -e s/two/YYY/', 'exit'],
        'stdout': [
            '.*exit status: 0.*',
            '.*exit status: 0.*',
            '.*exit status: 0.*',
        ],
        'allow_extra_stdout': True,
        'stderr': []
    },
    {
        'name': 'pipeline with two exit status 1s and one 0 has 1s',
        'input': ['/bin/true ignored 1 | /bin/false ignored 2 | /bin/false ignored 3', 'exit'],
        'stdout': [
            '.*exit status: 1.*',
            '.*exit status: 1.*',
        ],
        'allow_extra_stdout': True,
        'stderr': []
    },
    {
        'name': 'pipeline with two exit status 1s and one 0 has 0',
        'input': ['/bin/true some ignored arugments | /bin/false ignored argument | /bin/false more ignored argument', 'exit'],
        'stdout': [
            '.*exit status: 0.*',
        ],
        'allow_extra_stdout': True,
        'stderr': []
    },
    {
        'name': '100 pipelines (with limit of 50 open files)',
        'input': list(map(lambda i: '/bin/echo a test | /bin/sed -e s/test/xxx/', range(100))) + ['exit'],
        'stdout': list(map(lambda i: '.*a xxx', range(100))),
        'stderr': [],
        'allow_extra_stdout': True,
        'extra_popen': {
            'preexec_fn': lambda: resource.setrlimit(resource.RLIMIT_NOFILE, (50,50)),
        },
    },
    {
        'name': 'redirect from operator is invalid',
        'input': ['/bin/false < | ', 'exit'],
        'stdout': ['> > '],
        'stderr': ['.*invalid command.*'],
        'allow_extra_stderr': True,
    },
    {
        'name': 'large amount of data through pipe',
        'input': ['/usr/bin/head -c 1M /dev/zero | /bin/cat | /usr/bin/wc -c', 'exit'],
        'stdout': [ 
            '.*1048576.*',
            ],
        'stderr': [],
        'allow_extra_stdout': True,
        'timeout' : 30,
    },
]

TESTS = NON_PIPE_TESTS + PIPE_TESTS

def create_file(filename, contents):
    with open(filename, 'w') as fh:
        fh.write(contents)

def to_bytes(s):
    return bytes(s, 'UTF-8')

def bytes_to_lines(s):
    lines_as_bytes = s.split(b'\n')
    lines = list(map(lambda s: s.decode('UTF-8', errors='replace'), lines_as_bytes))
    return lines

def compare_lines(
        label,
        expected_lines,
        actual_lines,
        allow_extra_lines,
):
    errors = []
    actual_index = 0
    if len(actual_lines) > 0 and actual_lines[-1] == b'':
        actual_lines = actual_lines[:-1]
    for expected_line in map(to_bytes, expected_lines):
        pattern = re.compile(expected_line, re.IGNORECASE)
        prev_index = actual_index
        found_match = False
        while actual_index < len(actual_lines):
            actual_index += 1
            m = pattern.fullmatch(actual_lines[actual_index-1])
            if m != None:
                found_match = True
                break
            if not allow_extra_lines:
                errors.append('in {}: could not find a match for pattern [{}] in line [{}]'.format(
                    label,
                    expected_line.decode('UTF-8', errors='replace'),
                    actual_lines[actual_index-1].decode('UTF-8', errors='replace')
                ))
        if not found_match and actual_index >= len(actual_lines):
            errors.append('in {}: could not find match for pattern [{}] in {}'.format(
                label,
                expected_line.decode('UTF-8', errors='replace'),
                list(map(lambda x: x.decode('UTF-8', errors='replace'), actual_lines[prev_index:actual_index]))
            ))
            break
    if not allow_extra_lines and actual_index < len(actual_lines):
        errors.append('in {}: unexpected extra output [{}]'.format(label, list(map(lambda x: x.decode('UTF-8', errors='replace'), actual_lines[actual_index:]))))
    return errors

def run_test(
        input,
        stdout,
        stderr,
        allow_extra_stdout=False,
        allow_extra_stderr=False,
        timeout=5,
        name=None,
        extra_popen={},
        expect_output_files={},
        ignore_output_permissions=False,
        prepare_function=None,
        points=None, # ignored
        category=None, # ignored
        seperate_asan=False,
):
    for filename in expect_output_files.keys():
        if not filename.startswith('test/'):
            raise Exception("invalid test case: generated file not starting with test/")
        try:
            os.unlink(filename)
        except OSError:
            pass
    if prepare_function != None:
        prepare_function()
    errors = []
    input = b'\n'.join(map(to_bytes, input)) + b'\n'
    asan_temp = tempfile.TemporaryDirectory()
    if seperate_asan:
        my_env = os.environ.copy()
        my_env['ASAN_OPTIONS'] = 'halt_on_error=0:log_path={}/asan_log:print_legend=0:alloc_dealloc_mismatch=0'.format(asan_temp.name)
        extra_popen['env'] = my_env
    process = subprocess.Popen(
        PROGRAM,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **extra_popen
    )
    try:
        out_data, err_data = process.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired as to:
        out_data = to.output
        if out_data == None:
            out_data = b''
        if sys.version_info >= (3, 5):
            err_data = to.stderr
        else:
            err_data = b'<error output not available>'
        if err_data == None:
            err_data = b'<error output not available>'
        errors += [ 'timed out after {} seconds'.format(timeout) ]
    errors += compare_lines(
        'stdout',
        stdout,
        out_data.split(b'\n'),
        allow_extra_lines=allow_extra_stdout,
    )
    errors += compare_lines(
        'stderr',
        stderr,
        err_data.split(b'\n'),
        allow_extra_lines=allow_extra_stderr,
    )
    result = {
        'stdout': bytes_to_lines(out_data),
        'stderr': bytes_to_lines(err_data),
    }
    if seperate_asan:
        asan_errors = []
        asan_errors_children = []
        leak_error = False
        non_leak_error = False
        for asan_log_file in os.listdir(asan_temp.name):
            is_main = asan_log_file == 'asan_log.{}'.format(process.pid)
            if asan_log_file.startswith('asan_log.'):
                with open(os.path.join(asan_temp.name, asan_log_file), 'r') as fh:
                    for line in fh:
                        line = line.replace('\n','')
                        if is_main:
                            asan_errors.append(line)
                            if 'leak' in line:
                                leak_error = True
                            elif 'ERROR' in line:
                                non_leak_error = True
                        else:
                            asan_errors_children.append(line)
        result['asan_errors'] = asan_errors
        result['asan_errors_children'] = asan_errors_children
        result['asan_leak'] = leak_error
        result['asan_non_leak'] = non_leak_error
    for filename, expected_contents in sorted(expect_output_files.items()):
        try:
            if ignore_output_permissions:
                try:
                    if not os.access(filename, os.R_OK):
                        os.chmod(filename, 0o666)
                except OSError:
                    pass
            with open(filename, 'rb') as fh:
                lines = list(map(lambda x: x[:-1] if x.endswith(b'\n') else x, fh.readlines()))
                errors += compare_lines(
                    'created file {}'.format(filename),
                    expected_contents,
                    lines,
                    allow_extra_lines=False
                )
            os.unlink(filename)
        except OSError as e:
            if e.errno == errno.ENOENT:
                errors += [ 'file {} was not created'.format(filename) ]
            else:
                errors += [ 'error {} while reading {}'.format(e, filename) ]
    for filename in expect_output_files.keys():
        if not filename.startswith('test/'):
            raise Exception("invalid test case: generated file not starting with test/")
        try:
            os.unlink(filename)
        except OSError:
            pass
    result['errors'] = errors
    return result

def _output_with_limit(label, value, max_lines, output_to, annotate=None):
    annotate_string = "" if annotate == None else " ({})".format(annotate)
    print("{}:{}".format(label, annotate_string))
    if len(value) == 0:
        print("  <empty>", file=output_to)
    for line in value[0:max_lines]:
        print("  {}".format(line), file=output_to)
    if len(value) > max_lines:
        print("  [plus {} more lines, not shown]".format(len(value) - max_lines), file=output_to)

def run_and_output_tests(tests, max_lines=5, output_to=sys.stdout, verbose=False, seperate_asan=False):
    categories = {}
    total_passed = 0
    total_failed = 0
    total_score = 0
    total_possible = 0
    asan_leaks = 0
    asan_non_leaks = 0
    both_asan = 0
    for test in tests:
        name = test['name']
        category_name = test.get('category', '(none)')
        if category_name not in categories:
            categories[category_name] = {
                'possible': 0,
                'score': 0,
                'failed': [],
                'passed': [],
            }
        category = categories[category_name]
        points = test.get('points', 0)
        category['possible'] += points
        total_possible += points
        result = run_test(seperate_asan=seperate_asan, **test)
        errors = result['errors']
        if len(errors) == 0:
            total_passed += 1
            category['score'] += points
            total_score += points
            category['passed'].append(name)
            if verbose:
                print("Passed test", name, file=output_to)
            if result.get('asan_errors') != None:
                if len(result['asan_errors']) > 0:
                    _output_with_limit('AddressSanitizer output (main process)', result['asan_errors'], max_lines, output_to)
                if len(result['asan_errors_children']) > 0:
                    _output_with_limit('AddressSanitizer output (child processes)', result['asan_errors_children'], max_lines, output_to)
            asan_leaks += points if result.get('asan_leak', False) else 0
            asan_non_leaks += points if result.get('asan_non_leak', False) else 0
            both_asan += points if result.get('asan_leak', False) and result.get('asan_non_leak', False) else 0
        else:
            total_failed += 1
            print("Failed test", name, file=output_to)
            category['failed'].append(name)
            _output_with_limit('Test input', test['input'], max_lines, output_to)
            _output_with_limit('Actual stdout', result.get('stdout', '<unknown>'), max_lines, output_to)
            _output_with_limit('Actual stderr', result.get('stderr', '<unknown>'), max_lines, output_to)
            if result.get('asan_errors') != None:
                if len(result['asan_errors']) > 0:
                    _output_with_limit('AddressSanitizer output (main process)', result['asan_errors'], max_lines, output_to)
                if len(result['asan_errors_children']) > 0:
                    _output_with_limit('AddressSanitizer output (child processes)', result['asan_errors_children'], max_lines, output_to)
            _output_with_limit('Expected stdout regular expression pattern', test['stdout'], max_lines, output_to,
                "extra lines allowed" if test.get('allow_extra_stdout', False) else None
            )
            _output_with_limit('Expected stderr regular expression pattern', test['stderr'], max_lines, output_to,
                "extra lines allowed" if test.get('allow_extra_stderr', False) else None
            )
            if 'extra_popen' in test or 'prepare_function' in test:
                print("(This test also has some important extra setup code that might do something like restrict the number of file descriptors or child processes that can be created.)", file=output_to)
            _output_with_limit('Errors', errors, max_lines, output_to)
    return {
        'by_category': categories,
        'total_passed': total_passed,
        'total_failed': total_failed,
        'total_score': total_score,
        'total_possible': total_possible,
        'asan_leaks': asan_leaks,
        'asan_non_leaks': asan_non_leaks,
        'asan_leak_and_non_leaks': asan_non_leaks,
    }


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    if len(sys.argv) > 1 and sys.argv[1] == 'non-pipe':
        TESTS = NON_PIPE_TESTS
    elif len(sys.argv) > 1:
        raise Exception("Unrecognized arguments {}".format(sys.argv))
    result = run_and_output_tests(TESTS)
    print("{} tests passed and {} tests failed.".format(result['total_passed'], result['total_failed']))
    if result['total_failed'] > 0:
        print("""---
Note on interpreting test output patterns:
All expected values matched against a "regular expression" where:
    .* means any string (including empty strings)
    .+ means any string (excluding empty strings)
    everything is matched case-insensitively
""")


"""
Plugin tester
-------------

Utilities for testing plugins.

"""

import re
import sys
from warnings import warn

try:
    from io import StringIO
except ImportError:
    from io import StringIO
    
__all__ = ['PluginTester', 'run']


class PluginTester(object):
    """A mixin for testing nose plugins in their runtime environment.
    
    Subclass this and mix in unittest.TestCase to run integration/functional 
    tests on your plugin.  When setUp() is called, the stub test suite is 
    executed with your plugin so that during an actual test you can inspect the 
    artifacts of how your plugin interacted with the stub test suite.
    
    Class Variables
    ---------------
    - activate
    
      - the argument to send nosetests to activate the plugin
     
    - suitepath
    
      - if set, this is the path of the suite to test.  otherwise, you
        will need to use the hook, makeSuite()
      
    - plugins

      - the list of plugins to make available during the run. Note
        that this does not mean these plugins will be *enabled* during
        the run -- only the plugins enabled by the activate argument
        or other settings in argv or env will be enabled.
    
    - args
  
      - a list of arguments to add to the nosetests command, in addition to
        the activate argument
    
    - env
    
      - optional dict of environment variables to send nosetests

    """
    activate = None
    suitepath = None
    args = None
    env = {}
    argv = None
    plugins = []
    ignoreFiles = None
    
    def makeSuite(self):
        """returns a suite object of tests to run (unittest.TestSuite())
        
        If self.suitepath is None, this must be implemented. The returned suite 
        object will be executed with all plugins activated.  It may return 
        None.
        
        Here is an example of a basic suite object you can return ::
        
            >>> import unittest
            >>> class SomeTest(unittest.TestCase):
            ...     def runTest(self):
            ...         raise ValueError("Now do something, plugin!")
            ... 
            >>> unittest.TestSuite([SomeTest()]) # doctest: +ELLIPSIS
            <unittest.TestSuite tests=[<...SomeTest testMethod=runTest>]>
        
        """
        raise NotImplementedError
    
    def _execPlugin(self):
        """execute the plugin on the internal test suite.
        """
        from nose.config import Config
        from nose.core import TestProgram
        from nose.plugins.manager import PluginManager
        
        suite = None
        stream = StringIO()
        conf = Config(env=self.env,
                      stream=stream,
                      plugins=PluginManager(plugins=self.plugins))
        if self.ignoreFiles is not None:
            conf.ignoreFiles = self.ignoreFiles
        if not self.suitepath:
            suite = self.makeSuite()
            
        self.nose = TestProgram(argv=self.argv, config=conf, suite=suite,
                                exit=False)
        self.output = AccessDecorator(stream)
                                
    def setUp(self):
        """runs nosetests with the specified test suite, all plugins 
        activated.
        """
        self.argv = ['nosetests', self.activate]
        if self.args:
            self.argv.extend(self.args)
        if self.suitepath:
            self.argv.append(self.suitepath)            

        self._execPlugin()


class AccessDecorator(object):
    stream = None
    _buf = None
    def __init__(self, stream):
        self.stream = stream
        stream.seek(0)
        self._buf = stream.read()
        stream.seek(0)
    def __contains__(self, val):
        return val in self._buf
    def __iter__(self):
        return self.stream
    def __str__(self):
        return self._buf


def blankline_separated_blocks(text):
    block = []
    for line in text.splitlines(True):
        block.append(line)
        if not line.strip():
            yield "".join(block)
            block = []
    if block:
        yield "".join(block)


def remove_stack_traces(out):
    # this regexp taken from Python 2.5's doctest
    traceback_re = re.compile(r"""
        # Grab the traceback header.  Different versions of Python have
        # said different things on the first traceback line.
        ^(?P<hdr> Traceback\ \(
            (?: most\ recent\ call\ last
            |   innermost\ last
            ) \) :
        )
        \s* $                # toss trailing whitespace on the header.
        (?P<stack> .*?)      # don't blink: absorb stuff until...
        ^ (?P<msg> \w+ .*)   #     a line *starts* with alphanum.
        """, re.VERBOSE | re.MULTILINE | re.DOTALL)
    blocks = []
    for block in blankline_separated_blocks(out):
        blocks.append(traceback_re.sub(r"\g<hdr>\n...\n\g<msg>", block))
    return "".join(blocks)


def simplify_warnings(out):
    warn_re = re.compile(r"""
        # Cut the file and line no, up to the warning name
        ^.*:\d+:\s
        (?P<category>\w+): \s+        # warning category
        (?P<detail>.+) $ \n?          # warning message
        ^ .* $                        # stack frame
        """, re.VERBOSE | re.MULTILINE)
    return warn_re.sub(r"\g<category>: \g<detail>", out)


def remove_timings(out):
    return re.sub(
        r"Ran (\d+ tests?) in [0-9.]+s", r"Ran \1 in ...s", out)


def munge_nose_output_for_doctest(out):
    """Modify nose output to make it easy to use in doctests."""
    out = remove_stack_traces(out)
    out = simplify_warnings(out)
    out = remove_timings(out)
    return out.strip()


def run(*arg, **kw):
    """
    Specialized version of nose.run for use inside of doctests that
    test test runs.

    This version of run() prints the result output to stdout.  Before
    printing, the output is processed by replacing the timing
    information with an ellipsis (...), removing traceback stacks, and
    removing trailing whitespace.

    Use this version of run wherever you are writing a doctest that
    tests nose (or unittest) test result output.

    Note: do not use doctest: +ELLIPSIS when testing nose output,
    since ellipses ("test_foo ... ok") in your expected test runner
    output may match multiple lines of output, causing spurious test
    passes!
    """
    from nose import run
    from nose.config import Config
    from nose.plugins.manager import PluginManager

    buffer = StringIO()
    if 'config' not in kw:
        plugins = kw.pop('plugins', [])
        if isinstance(plugins, list):
            plugins = PluginManager(plugins=plugins)
        env = kw.pop('env', {})
        kw['config'] = Config(env=env, plugins=plugins)
    if 'argv' not in kw:
        kw['argv'] = ['nosetests', '-v']
    kw['config'].stream = buffer
    
    # Set up buffering so that all output goes to our buffer,
    # or warn user if deprecated behavior is active. If this is not
    # done, prints and warnings will either be out of place or
    # disappear.
    stderr = sys.stderr
    stdout = sys.stdout
    if kw.pop('buffer_all', False):
        sys.stdout = sys.stderr = buffer
        restore = True
    else:
        restore = False
        warn("The behavior of nose.plugins.plugintest.run() will change in "
             "the next release of nose. The current behavior does not "
             "correctly account for output to stdout and stderr. To enable "
             "correct behavior, use run_buffered() instead, or pass "
             "the keyword argument buffer_all=True to run().",
             DeprecationWarning, stacklevel=2)
    try:
        run(*arg, **kw)
    finally:
        if restore:
            sys.stderr = stderr
            sys.stdout = stdout
    out = buffer.getvalue()
    print(munge_nose_output_for_doctest(out))

    
def run_buffered(*arg, **kw):
    kw['buffer_all'] = True
    run(*arg, **kw)

if __name__ == '__main__':
    import doctest
    doctest.testmod()

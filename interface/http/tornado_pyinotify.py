#!/usr/bin/env python

import pyinotify
from pyinotify import deque, _SysProcessEvent
from tornado.ioloop import IOLoop

class TornadoNotifier(pyinotify.Notifier):
    def __init__(self, watch_manager, default_proc_fun=None, read_freq=0,
                     threshold=0, timeout=None, io_loop = None):
        """
        Initialization. read_freq, threshold and timeout parameters are used
        when looping.

        @param watch_manager: Watch Manager.
        @type watch_manager: WatchManager instance
        @param default_proc_fun: Default processing method. If None, a new
                                 instance of PrintAllEvents will be assigned.
        @type default_proc_fun: instance of ProcessEvent
        @param read_freq: if read_freq == 0, events are read asap,
                          if read_freq is > 0, this thread sleeps
                          max(0, read_freq - timeout) seconds. But if
                          timeout is None it may be different because
                          poll is blocking waiting for something to read.
        @type read_freq: int
        @param threshold: File descriptor will be read only if the accumulated
                          size to read becomes >= threshold. If != 0, you likely
                          want to use it in combination with an appropriate
                          value for read_freq because without that you would
                          keep looping without really reading anything and that
                          until the amount of events to read is >= threshold.
                          At least with read_freq set you might sleep.
        @type threshold: int
        @param timeout:
            http://docs.python.org/lib/poll-objects.html#poll-objects
        @type timeout: int
        """
        # Watch Manager instance
        self._watch_manager = watch_manager
        # File descriptor
        self._fd = self._watch_manager.get_fd()
        # Poll object and registration
        #self._pollobj = select.poll()
        #self._pollobj.register(self._fd, select.POLLIN)
        if io_loop is None:
            raise ValueError('io_loop must be specified')

        io_loop.add_handler(self._fd, self.handle_tornado, IOLoop.READ)
        
        # This pipe is correctely initialized and used by ThreadedNotifier
        self._pipe = (-1, -1)
        # Event queue
        self._eventq = deque()
        # System processing functor, common to all events
        self._sys_proc_fun = _SysProcessEvent(self._watch_manager, self)
        # Default processing method
        self._default_proc_fun = default_proc_fun
        if default_proc_fun is None:
            self._default_proc_fun = PrintAllEvents()
        # Loop parameters
        self._read_freq = read_freq
        self._threshold = threshold
        self._timeout = timeout
        # Coalesce events option
        self._coalesce = False
        # set of str(raw_event), only used when coalesce option is True
        self._eventset = set()


    def handle_tornado(self, fd, event):
        self.read_events()
        self.process_events()
        
        

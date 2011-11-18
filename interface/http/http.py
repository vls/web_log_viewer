#!/usr/bin/env python
import os
import time
import re

import tornado
from tornado import ioloop, httpserver, websocket
import tornado.ioloop
import tornado.web

import logging


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/tail/?", TailHandler),
            (r"/websocket/tail/(?P<filename>.*)", WSTailHandler),
            (r"/", MainHandler),
        ] 
        settings = dict(
            static_path = os.path.join(os.path.dirname(__file__), "static"),
            template_path = os.path.join(os.path.dirname(__file__), "tmpl"), 
            basic_path = '/tmp',
        )
        tornado.web.Application.__init__(self, handlers, **settings)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render('index.html')



class TailMixin(object):
    line_terminators = ('\r\n', '\n', '\r')
    read_size = 1024

    def seek(self, pos, whence=0):
        self.fd.seek(pos, whence)

    def tail(self, lines=10):
        """\
        Return the last lines of the file.
        """
        self.seek_end()
        end_pos = self.fd.tell()

        for i in xrange(lines):
            if not self.seek_line():
                break

        data = self.fd.read(end_pos - self.fd.tell() - 1)
        if data:
            return self.splitlines(data)
        else:
            return []

    def seek_line(self):
        """\
        Searches backwards from the current file position for a line terminator
        and seeks to the charachter after it.
        """
        pos = end_pos = self.fd.tell()

        read_size = self.read_size
        if pos > read_size:
            pos -= read_size
        else:
            pos = 0
            read_size = end_pos

        self.seek(pos)

        bytes_read, read_str = self.read(read_size)

        if bytes_read and read_str[-1] in self.line_terminators:
            # The last charachter is a line terminator, don't count this one
            bytes_read -= 1

            if read_str[-2:] == '\r\n' and '\r\n' in self.line_terminators:
                # found crlf
                bytes_read -= 1

        while bytes_read > 0:          
            # Scan backward, counting the newlines in this bufferfull
            i = bytes_read - 1
            while i >= 0:
                if read_str[i] in self.line_terminators:
                    self.seek(pos + i + 1)
                    return self.fd.tell()
                i -= 1

            if pos == 0 or pos - self.read_size < 0:
                # Not enought lines in the buffer, send the whole file
                self.seek(0)
                return None

            pos -= self.read_size
            self.seek(pos)

            bytes_read, read_str = self.read(self.read_size)

        return None

    def read(self, read_size=None):
        if read_size:
            read_str = self.fd.read(read_size)
        else:
            read_str = self.fd.read()

        return len(read_str), read_str

    def splitlines(self, data):
        return re.split('|'.join(self.line_terminators), data)

    def seek_end(self):
        self.seek(0, 2)

class CallbackTailMixin(TailMixin):
    def setfd(self, fd):
        self.fd = fd

    def on_line(self, line):
        pass

    def follow(self):
        while True:
            where = self.fd.tell()
            line = self.fd.readline()
            if line:    
                if self.trailing and line in self.line_terminators:
                    # This is just the line terminator added to the end of the file
                    # before a new line, ignore.
                    trailing = False
                    self.timeout_handle = ioloop.IOLoop.instance().add_timeout(time.time() + 0.1, self.follow)
                    return

                if line[-1] in self.line_terminators:
                    line = line[:-1]
                    if line[-1:] == '\r\n' and '\r\n' in self.line_terminators:
                        # found crlf
                        line = line[:-1]

                self.trailing = False
                self.on_line(line)
            else:
                self.trailing = True
                self.seek(where)
                self.timeout_handle = ioloop.IOLoop.instance().add_timeout(time.time() + 0.1, self.follow)
                break

        

class TailFileClient(CallbackTailMixin):
    def __init__(self, filename, init_lines = 10):
        fd = open(filename, 'r')
        self.setfd(fd)
        self.waiters = set()
        #self.set_line_callback(callback)
        self.init_lines = init_lines
        self.trailing = True
        self.timeout_handle = None

    def on_line(self, line, cl = None):
        if cl is not None:
            cl.on_line(line)
            return

        for cl in self.waiters:
            try:
                cl.on_line(line)
            except:
                pass


    def start(self, single = None):
        init_lines = self.init_lines
        if init_lines and isinstance(init_lines, (int, long)):
            lines = self.tail(init_lines)
            for line in lines:
                self.on_line(line, cl = single)

        self.follow()

    def close(self):
        if self.timeout_handle:
            ioloop.IOLoop.instance().remove_timeout(self.timeout_handle)

        if self.fd:
            self.fd.close()
        

def log(msg):
    print msg


class WSTailHandler(websocket.WebSocketHandler):
    clients = {}

    def on_line(self, line):
        self.write_message(line + '\n')

    def _request_income(self):
        cls = WSTailHandler
        obj = cls.clients.get(self.filename, None)
        flagFirst = False
        if obj is None:
            #first request
            flagFirst = True
            log("first request for %s" % self.filename)
            obj = TailFileClient(self.filename)
            cls.clients[self.filename] = obj
        else:
            log("incomeing request for %s" % self.filename)
        obj.waiters.add(self)

        if flagFirst:
            obj.start()
        else:
            obj.start(single = self)


    def on_close(self):
        cls = WSTailHandler
        tfc = cls.clients.get(self.filename)

        tfc.waiters.remove(self)
        if not tfc.waiters:
            tfc.close()
            del cls.clients[self.filename]
            


    def open(self, *args, **kwargs):
        print 'ws incoming.. args = %s, kwargs = %s' % (args, kwargs)
        try:
            #filename = self.get_argument('filename', None)
            filename = kwargs.get('filename', None)
            if filename:
                basic_path = self.settings['basic_path']
                fullpath = os.path.normpath(os.path.join(basic_path, filename))
                if not fullpath.startswith(basic_path):
                    self.write_message('".." is not allowed in filename')
                    return

                self.filename = fullpath
                self._request_income()
            else:
                self.write_message('no filename')
        except IOError, e:
            print e

    def on_message(self, msg):
        print "get msg: %s" % msg



    
    
class TailHandler(tornado.web.RequestHandler, TailMixin):
    @tornado.web.asynchronous
    def get(self):
        try:
            filename = self.get_argument('filename', None)
            if filename:
                basic_path = self.settings['basic_path']
                fullpath = os.path.normpath(os.path.join(basic_path, filename))
                if not fullpath.startswith(basic_path):
                    self.write('".." is not allowed in filename')
                    self.finish()
                    return

                self.fd = open(fullpath, 'r')
                self.read_size = 1024

                lines = self.tail(10)
                for line in lines:
                    print line
                    self.write(line)
                    self.write('\n')
                    self.flush()

                self.trailing = True       
                self.follow()
            else:
                self.write('no filename')
                self.finish()
        except IOError, e:
            print e


    def follow(self):
        if self.request.connection.stream.closed():
            print 'client closed'
            return
        
        while True:
            where = self.fd.tell()
            line = self.fd.readline()
            if line:    
                if self.trailing and line in self.line_terminators:
                    # This is just the line terminator added to the end of the file
                    # before a new line, ignore.
                    trailing = False
                    ioloop.IOLoop.instance().add_timeout(time.time() + 0.1, self.follow)
                    return

                if line[-1] in self.line_terminators:
                    line = line[:-1]
                    if line[-1:] == '\r\n' and '\r\n' in self.line_terminators:
                        # found crlf
                        line = line[:-1]

                self.trailing = False
                self.write(line)
                self.write('\n')
                self.flush()
            else:
                self.trailing = True
                self.seek(where)
                ioloop.IOLoop.instance().add_timeout(time.time() + 0.1, self.follow)
                break







        
        


def main():
    app = Application()
    http_server = httpserver.HTTPServer(app)
    http_server.listen(18080)
    print tornado
    ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    main()

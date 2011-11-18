#!/usr/bin/env python
import sys, os
import shlex
import subprocess
import getopt

def usage():
    print "%s -c" % sys.argv[0]

def main():

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'c:o:e:')
    except getopt.GetoptError, err:
        print str(err)
        usage()
        sys.exit(1)

    output = None
    env = None
    cmdline = None
    error_output = None
    for o, a in opts:
        if o == '-o':
            output = a
        elif o == '-c':
            cmdline = a
        elif o == '-e':
            error_output = a

    if env is None:
        env = os.environ

    args = shlex.split(cmdline, posix = True)
    
    fd_out = fd_err = subprocess.STDOUT
    if output:
        fd_out = open(output, 'a+')
        fd_err = open(error_output if error_output else output, 'a+')

    p = subprocess.Popen(args, stdout = fd_out, stderr = fd_err)
    p.wait()




if __name__ == '__main__':
    main()

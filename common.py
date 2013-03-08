import sys

def statusmsg(*args):
    if sys.stdout.isatty():
        print "\x1b[35;1m>>> ", " ".join(args), "\x1b[0m"
    else:
        print ">>> ".join(args)

def errormsg(*args):
    if sys.stdout.isatty():
        print "\x1b[31;1m*** ", " ".join(args), "\x1b[0m"
    else:
        print "*** ".join(args)



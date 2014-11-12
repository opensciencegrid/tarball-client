'''Module to write the template setup.sh and setup.csh files

This is scripted because the contents of the setup files depend on the dver and
the basearch of the tarball they will be part of.

We need to write both a setup.csh.in and a setup.sh.in, and aside from the
syntax, their contents will be identical. With the shell_construct hash, we
get rid of a lot of the duplication.

shell_construct is a hash of hashes. The first key is the shell family, and the
second key identifies a shell construct -- a statement or fragment of a
statement. For example, the 'setenv' construct is to set an environment
variable.  In csh, it expands to 'setenv var "value"', and in sh, it expands to
'export var="value"'.  Each sub-hash must have the same keys.
Constructs that have arguments are lambdas; those that do not are strings.
'''

import os
import sys

def write_to_file(dest_path, text_to_write):
    dest_fh = open(dest_path, 'w')
    try:
        dest_fh.write(text_to_write)
    finally:
        dest_fh.close()


shell_construct = {
    'csh': {
        'setenv'     : (lambda var,value : 'setenv %s "%s"\n' % (var,value)),
        'ifdef'      : (lambda var       : 'if ($?%s) then\n' % var),
        'ifreadable' : (lambda fname     : 'if -r "%s" then\n' % fname),
        'else'       : 'else\n',
        'endif'      : 'endif\n',
        'source'     : (lambda fname     : 'source "%s"\n' % (fname)),
    },
    'sh': {
        'setenv'     : (lambda var,value : 'export %s="%s"\n' % (var,value)),
        'ifdef'      : (lambda var       : 'if [ "X" != "X${%s-}" ]; then\n' % var),
        'ifreadable' : (lambda fname     : 'if [ -r "%s" ]; then\n' % fname),
        'else'       : 'else\n',
        'endif'      : 'fi\n',
        'source'     : (lambda fname     : '. "%s"\n' % (fname)),
    }
}



def write_setup_in_files(dest_dir, dver, basearch):
    '''Writes dest_dir/setup.csh.in and dest_dir/setup.sh.in according to the
    dver and basearch provided.

    '''

    if basearch == 'i386':
        osg_ld_library_path = ":".join([
            "$OSG_LOCATION/usr/lib",
            "$OSG_LOCATION/usr/lib/dcap",
            "$OSG_LOCATION/usr/lib/lcgdm"])
    elif basearch == 'x86_64':
        osg_ld_library_path = ":".join([
            "$OSG_LOCATION/usr/lib64",
            "$OSG_LOCATION/usr/lib", # search 32-bit libs too
            "$OSG_LOCATION/usr/lib64/dcap",
            "$OSG_LOCATION/usr/lib64/lcgdm"])
    else:
        raise Exception("Unknown basearch %r" % basearch)

    if dver == 'el5':
        osg_perl5lib = "$OSG_LOCATION/usr/lib/perl5/vendor_perl/5.8.8"
    elif dver == 'el6':
        osg_perl5lib = ":".join([
            "$OSG_LOCATION/usr/share/perl5/vendor_perl",
            "$OSG_LOCATION/usr/share/perl5"])
    else:
        raise Exception("Unknown dver %r" % dver)

    # Arch-independent python stuff always goes in usr/lib/, even on x86_64
    if dver == 'el5':
        osg_pythonpath = "$OSG_LOCATION/usr/lib/python2.4/site-packages"
        if basearch == 'x86_64':
            osg_pythonpath += ":$OSG_LOCATION/usr/lib64/python2.4/site-packages"
    elif dver == 'el6':
        osg_pythonpath = "$OSG_LOCATION/usr/lib/python2.6/site-packages"
        if basearch == 'x86_64':
            osg_pythonpath += ":$OSG_LOCATION/usr/lib64/python2.6/site-packages"
    else:
        raise Exception("Unknown dver %r" % dver)

    osg_manpath = "$OSG_LOCATION/usr/share/man"


    for sh in 'csh', 'sh':
        dest_path = os.path.join(dest_dir, 'setup.%s.in' % sh)
        text_to_write = "# Source this file if using %s or a shell derived from it\n" % sh
        setup_local = "$OSG_LOCATION/setup-local.%s" % sh

        _setenv     = shell_construct[sh]['setenv']
        _ifdef      = shell_construct[sh]['ifdef']
        _else       = shell_construct[sh]['else']
        _endif      = shell_construct[sh]['endif']
        _ifreadable = shell_construct[sh]['ifreadable']
        _source     = shell_construct[sh]['source']

        # Set OSG_LOCATION first because all the other variables depend on it
        text_to_write += _setenv("OSG_LOCATION", "@@OSG_LOCATION@@")

        for variable, value in [
                ("GLOBUS_LOCATION", "$OSG_LOCATION/usr"),
                ("PATH",            "$OSG_LOCATION/usr/bin:$OSG_LOCATION/usr/sbin:$PATH"),
                ("X509_CERT_DIR",   "$OSG_LOCATION/etc/grid-security/certificates"),
                ("X509_VOMS_DIR",   "$OSG_LOCATION/etc/grid-security/vomsdir"),
                ("VOMS_USERCONF",   "$OSG_LOCATION/etc/vomses")]:

            text_to_write += _setenv(variable, value)

        for variable, value in [
                ("LD_LIBRARY_PATH", osg_ld_library_path),
                ("PERL5LIB",        osg_perl5lib),
                ("PYTHONPATH",      osg_pythonpath),
                ("MANPATH",         osg_manpath)]:

            text_to_write += (
                 _ifdef(variable)
               + "\t" + _setenv(variable, value + ":$" + variable)
               + _else
               + "\t" + _setenv(variable, value)
               + _endif
               + "\n")

        text_to_write += (
              "\n"
            + "# Site-specific customizations\n"
            + _ifreadable(setup_local)
            + "\t" + _source(setup_local)
            + _endif
            + "\n")

        write_to_file(dest_path, text_to_write)


def main(argv):
    dest_dir, dver, basearch = argv[1:4]
    write_setup_in_files(dest_dir, dver, basearch)

if __name__ == '__main__':
    sys.exit(main(sys.argv))


"""
The MIT License (MIT)

Copyright (c) [2015-2021] [Andrew Annex]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Sources for this file are mostly from DaRasch, spiceminer/getcspice.py,
with edits by me as needed for python2/3 compatibility
https://github.com/DaRasch/spiceminer/blob/master/getcspice.py

The MIT License (MIT)

Copyright (c) 2013 Philipp Rasch

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

The MIT License (MIT)

Copyright (c) 2017 ODC Space

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""
import io
import platform
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tempfile
import urllib
import urllib.request
import urllib.error
from zipfile import ZipFile

CSPICE_SRC_DIR = "CSPICE_SRC_DIR"
CSPICE_SHARED_LIB = "CSPICE_SHARED_LIB"
CSPICE_NO_PATCH = "CSPICE_NO_PATCH"

host_OS = platform.system()
# Check if platform is supported
os_supported = host_OS in ("Linux", "Darwin", "FreeBSD", "Windows")
# Get platform is Unix-like OS or not
is_unix = host_OS in ("Linux", "Darwin", "FreeBSD")
# Get current working directory
root_dir = os.path.dirname(os.path.realpath(__file__))
# Make the directory path for cspice
cspice_dir = os.environ.get(CSPICE_SRC_DIR, os.path.join(root_dir, "cspice"))
# Make the directory path for cspice/lib
lib_dir = os.path.join(cspice_dir, "lib")
# and make a global tmp cspice directory
tmp_cspice_dir_name = None
# versions
spice_version = "N0066"
spice_num_v = "66"


class GetCSPICE(object):
    """
    Class that support the download from the NAIF FTP server of the required
    CSPICE package for the architecture used by the Python distribution that
    invokes this module.  By default the CSPICE Toolkit version N0066 is
    downloaded and unpacked on the directory where this module is located.

    Arguments
    ---------
    :argument version: String indicating the required version of the CSPICE
                       Toolkit. By default it is 'N0066'.
    :type: str

    """

    # This class variable will be used to store the CSPICE package in memory.
    _local = None

    # Supported distributions
    _dists = {
        # system   arch        distribution name           extension
        # -------- ----------  -------------------------   ---------
        ("Darwin", "32bit"): ("MacIntel_OSX_AppleC_32bit", "tar.Z"),
        ("Darwin", "64bit"): ("MacIntel_OSX_AppleC_64bit", "tar.Z"),
        ("cygwin", "32bit"): ("PC_Cygwin_GCC_32bit", "tar.Z"),
        ("cygwin", "64bit"): ("PC_Cygwin_GCC_64bit", "tar.Z"),
        ("FreeBSD", "32bit"): ("PC_Linux_GCC_32bit", "tar.Z"),
        ("FreeBSD", "64bit"): ("PC_Linux_GCC_64bit", "tar.Z"),
        ("Linux", "32bit"): ("PC_Linux_GCC_32bit", "tar.Z"),
        ("Linux", "64bit"): ("PC_Linux_GCC_64bit", "tar.Z"),
        ("Windows", "32bit"): ("PC_Windows_VisualC_32bit", "zip"),
        ("Windows", "64bit"): ("PC_Windows_VisualC_64bit", "zip"),
    }

    def __init__(self, version=spice_version, dst=None):
        """Init method that uses either the default N0066 toolkit version token
        or a user provided one.
        """
        try:
            # Get the remote file path for the Python architecture that
            # executes the script.
            distribution, self._ext = self._distribution_info()
        except KeyError:
            print("SpiceyPy currently does not support your system.")
        else:
            cspice = "cspice.{}".format(self._ext)
            self._rcspice = (
                "https://naif.jpl.nasa.gov/pub/naif/misc"
                "/toolkit_{0}/C/{1}/packages"
                "/{2}"
            ).format(version, distribution, cspice)

            # Setup the local directory (where the package will be downloaded)
            if dst is None:
                dst = os.path.realpath(os.path.dirname(__file__))
            self._root = dst

            # Download the file
            print("Downloading CSPICE for {0}...".format(distribution))
            attempts = 10  # Let's try a maximum of attempts for getting SPICE
            while attempts:
                attempts -= 1
                try:
                    self._download()
                except RuntimeError as error:
                    print(
                        "Download failed with URLError: {0}, trying again after "
                        "15 seconds!".format(error)
                    )
                    time.sleep(15)
                else:
                    # Unpack the file
                    print("Unpacking... (this may take some time!)")
                    self._unpack()
                    # We are done.  Let's return to the calling code.
                    break

    def _distribution_info(self):
        """Creates the distribution name and the expected extension for the
        CSPICE package and returns it.

        :return (distribution, extension) tuple where distribution is the best
                guess from the strings available within the platform_urls list
                of strings, and extension is either "zip" or "tar.Z" depending
                on whether we are dealing with a Windows platform or else.
        :rtype: tuple (str, str)

        :raises: KeyError if the (system, machine) tuple does not correspond
                 to any of the supported SpiceyPy environments.
        """

        print("Gathering information...")
        system = platform.system()

        # Cygwin system is CYGWIN-NT-xxx.
        system = "cygwin" if "CYGWIN" in system else system

        processor = platform.processor()
        machine = "64bit" if sys.maxsize > 2 ** 32 else "32bit"
        machine2 = platform.machine()

        print("SYSTEM:   ", system)
        print("PROCESSOR:", processor)
        print("MACHINE:  ", machine, machine2)

        return self._dists[(system, machine)]

    def _download(self):
        """Support function that encapsulates the OpenSSL transfer of the CSPICE
        package to the self._local io.ByteIO stream.

        :raises RuntimeError if there has been any issue with the HTTPS
                             communication

        .. note::

           Handling of CSPICE downloads from HTTPS
           ---------------------------------------
           Some Python distributions may be linked to an old version of OpenSSL
           which will not let you connect to NAIF server due to recent SSL cert
           upgrades on the JPL servers.  Moreover, versions older than
           OpenSSL 1.0.1g are known to contain the 'the Heartbleed Bug'.
           Therefore this method provides two different implementations for the
           HTTPS GET call to the NAIF server to download the required CSPICE
           distribution package.

           * as of 3.0.1, we default back to use built in openssl, as we require python 3.6 or above *
        """
        try:
            # Send the request to get the CSPICE package (proxy auto detected).
            response = urllib.request.urlopen(self._rcspice, timeout=10)
        except urllib.error.URLError as err:
            raise RuntimeError(err.reason)

        # Convert the response to io.BytesIO and store it in local memory.
        self._local = io.BytesIO(response.read())

    def _unpack(self):
        """Unpacks the CSPICE package on the given root directory. Note that
        Package could either be the zipfile.ZipFile class for Windows platforms
        or tarfile.TarFile for other platforms.
        """
        if self._ext == "zip":
            with ZipFile(self._local, "r") as archive:
                archive.extractall(self._root)
        else:
            cmd = "gunzip | tar xC " + self._root
            proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE)
            proc.stdin.write(self._local.read())
        self._local.close()


def copy_supplements() -> None:
    """
    Copy supplement files (patches, windows build files)
    to cspice directory
    """
    patches = list(Path().cwd().glob("*.patch"))
    print("copy: ", cspice_dir)
    for p in patches:
        shutil.copy(p, cspice_dir)
    if host_OS == "Windows":
        windows_files = [Path("./makeDynamicSpice.bat"), Path("./cspice.def")]
        cspice_src_dir = os.path.join(cspice_dir, "cspice", "src", "cspice")
        for w in windows_files:
            shutil.copy(w, cspice_src_dir)


def apply_patches() -> None:
    os.chdir(cspice_dir)
    iswin = "-windows" if host_OS == "Windows" else ""
    patches = [
        f"0001-patch-for-n66-dskx02.c{iswin}.patch",
        f"0002-patch-for-n66-subpnt.c{iswin}.patch",
    ]
    if host_OS == "Darwin":  # todo is this only needed for M1 or is it for any macos
        patches.append("0004_inquire_unistd.patch")
    for p in patches:
        try:
            patch_cmd = subprocess.run(["git", "apply", "--reject", p], check=True)
        except subprocess.CalledProcessError as cpe:
            raise cpe
    pass


def prepare_cspice() -> None:
    """
    Prepare temporary cspice source directory,
    If not provided by the user, or if not readable, download a fresh copy
    :return: None
    """
    global cspice_dir, lib_dir, tmp_cspice_dir_name
    tmp_cspice_dir = tempfile.TemporaryDirectory(prefix="cspice_spiceypy_")
    tmp_cspice_dir_name = os.path.realpath(tmp_cspice_dir.name)
    # Trick for python <3.8, delete tmp dir so that we can write it over
    tmp_cspice_dir.cleanup()
    if os.access(cspice_dir, os.R_OK):
        print("Found usable CSPICE src directory")
        # newer shutil.copytree has a flag for this that negates need for this
        shutil.copytree(
            cspice_dir + "/",
            tmp_cspice_dir_name + "cspice/",
            copy_function=shutil.copy,
        )
    else:
        Path(tmp_cspice_dir_name).mkdir(exist_ok=True, parents=True)
        print("Downloading CSPICE src from NAIF")
        GetCSPICE(dst=tmp_cspice_dir_name)
    cspice_dir = tmp_cspice_dir_name
    lib_dir = os.path.join(tmp_cspice_dir_name, "lib")
    print("end of prep:", cspice_dir)
    # okay now copy any and all files needed for building
    pass


def build_cspice() -> str:
    """
    Builds cspice
    :return: absolute path to new compiled shared library
    """
    global cspice_dir, host_OS
    if is_unix:
        libname = f"libcspice.so"
        if host_OS == "Darwin":
            extra_flags = f"-dynamiclib -install_name @rpath/{libname}"
        else:
            extra_flags = f"-shared -Wl,-soname,{libname}"
        destination = cspice_dir
        os.chdir(destination)
        cmds = [
            "gcc -Iinclude -c -fPIC -O2 -ansi -pedantic ./cspice/src/cspice/*.c",
            f"gcc {extra_flags} -fPIC -O2 -pedantic -lm *.o -o {libname}",
        ]
    elif host_OS == "Windows":
        destination = os.path.join(cspice_dir, "cspice", "src", "cspice")
        os.chdir(destination)
        cmds = ["makeDynamicSpice.bat"]
    else:
        raise NotImplementedError(f"non implemented host os for build {host_OS}")
    try:
        for cmd in cmds:
            _ = subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as cpe:
        pass
    # get the built shared library
    shared_lib_path = [
        str(p.absolute())
        for p in Path(destination).glob("*.*")
        if p.suffix in (".dll", ".66", ".dylib", ".so")
    ]
    if len(shared_lib_path) != 1:
        raise RuntimeError(
            f'Could not find built shared library of SpiceyPy in {list(Path(destination).glob("*.*"))}'
        )
    else:
        shared_lib_path = shared_lib_path[0]
    return shared_lib_path


def get_spice() -> None:
    """
    Main routine to build or not spice
    :return: None
    """
    # set final destination for cspice dynamic library
    destination = os.path.join(
        root_dir, "spiceypy", "utils", "libcspice.so" if is_unix else "libcspice.dll"
    )
    # first see if cspice shared library is provided
    shared_library_path = os.environ.get(CSPICE_SHARED_LIB)
    if shared_library_path is not None:
        print(f"User has provided a shared library...")
        # todo: what if we can't read the file? we need to jump to building it... doubtful this happens
        pass  # now we don't need to do that much
    else:
        # okay, now we either are given a src dir, have already downloaded it, or don't have it
        print("Preparing cspice")
        prepare_cspice()
        # add the patches
        print("Copying supplements")
        copy_supplements()
        # okay now that we have the source in a writeable directory we can apply patches
        if CSPICE_NO_PATCH not in os.environ:
            print("Apply patches")
            apply_patches()
        # now build
        print("Building cspice")
        shared_library_path = build_cspice()
    # okay now move shared library to dst dir
    shutil.copyfile(shared_library_path, destination)
    # cleanup tmp dir
    if tmp_cspice_dir_name is not None:
        if os.path.exists(tmp_cspice_dir_name) and os.path.isdir(tmp_cspice_dir_name):
            shutil.rmtree(tmp_cspice_dir_name)
    # and now we are done!
    print("Done!")


if __name__ == "__main__":
    get_spice()

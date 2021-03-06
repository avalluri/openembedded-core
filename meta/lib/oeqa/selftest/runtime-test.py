from oeqa.selftest.base import oeSelfTest
from oeqa.utils.commands import runCmd, bitbake, get_bb_var, get_bb_vars, runqemu
from oeqa.utils.decorators import testcase
import os
import re

class TestExport(oeSelfTest):

    @classmethod
    def tearDownClass(cls):
        runCmd("rm -rf /tmp/sdk")

    def test_testexport_basic(self):
        """
        Summary: Check basic testexport functionality with only ping test enabled.
        Expected: 1. testexport directory must be created.
                  2. runexported.py must run without any error/exception.
                  3. ping test must succeed.
        Product: oe-core
        Author: Mariano Lopez <mariano.lopez@intel.com>
        """

        features = 'INHERIT += "testexport"\n'
        # These aren't the actual IP addresses but testexport class needs something defined
        features += 'TEST_SERVER_IP = "192.168.7.1"\n'
        features += 'TEST_TARGET_IP = "192.168.7.1"\n'
        features += 'TEST_SUITES = "ping"\n'
        self.write_config(features)

        # Build tesexport for core-image-minimal
        bitbake('core-image-minimal')
        bitbake('-c testexport core-image-minimal')

        testexport_dir = get_bb_var('TEST_EXPORT_DIR', 'core-image-minimal')

        # Verify if TEST_EXPORT_DIR was created
        isdir = os.path.isdir(testexport_dir)
        self.assertEqual(True, isdir, 'Failed to create testexport dir: %s' % testexport_dir)

        with runqemu('core-image-minimal') as qemu:
            # Attempt to run runexported.py to perform ping test
            test_path = os.path.join(testexport_dir, "oe-test")
            data_file = os.path.join(testexport_dir, 'data', 'testdata.json')
            manifest = os.path.join(testexport_dir, 'data', 'manifest')
            cmd = ("%s runtime --test-data-file %s --packages-manifest %s "
                   "--target-ip %s --server-ip %s --quiet"
                  % (test_path, data_file, manifest, qemu.ip, qemu.server_ip))
            result = runCmd(cmd)
            # Verify ping test was succesful
            self.assertEqual(0, result.status, 'oe-test runtime returned a non 0 status')

    def test_testexport_sdk(self):
        """
        Summary: Check sdk functionality for testexport.
        Expected: 1. testexport directory must be created.
                  2. SDK tarball must exists.
                  3. Uncompressing of tarball must succeed.
                  4. Check if the SDK directory is added to PATH.
                  5. Run tar from the SDK directory.
        Product: oe-core
        Author: Mariano Lopez <mariano.lopez@intel.com>
        """

        features = 'INHERIT += "testexport"\n'
        # These aren't the actual IP addresses but testexport class needs something defined
        features += 'TEST_SERVER_IP = "192.168.7.1"\n'
        features += 'TEST_TARGET_IP = "192.168.7.1"\n'
        features += 'TEST_SUITES = "ping"\n'
        features += 'TEST_EXPORT_SDK_ENABLED = "1"\n'
        features += 'TEST_EXPORT_SDK_PACKAGES = "nativesdk-tar"\n'
        self.write_config(features)

        # Build tesexport for core-image-minimal
        bitbake('core-image-minimal')
        bitbake('-c testexport core-image-minimal')

        needed_vars = ['TEST_EXPORT_DIR', 'TEST_EXPORT_SDK_DIR', 'TEST_EXPORT_SDK_NAME']
        bb_vars = get_bb_vars(needed_vars, 'core-image-minimal')
        testexport_dir = bb_vars['TEST_EXPORT_DIR']
        sdk_dir = bb_vars['TEST_EXPORT_SDK_DIR']
        sdk_name = bb_vars['TEST_EXPORT_SDK_NAME']

        # Check for SDK
        tarball_name = "%s.sh" % sdk_name
        tarball_path = os.path.join(testexport_dir, sdk_dir, tarball_name)
        msg = "Couldn't find SDK tarball: %s" % tarball_path
        self.assertEqual(os.path.isfile(tarball_path), True, msg)

        # Extract SDK and run tar from SDK
        result = runCmd("%s -y -d /tmp/sdk" % tarball_path)
        self.assertEqual(0, result.status, "Couldn't extract SDK")

        env_script = result.output.split()[-1]
        result = runCmd(". %s; which tar" % env_script, shell=True)
        self.assertEqual(0, result.status, "Couldn't setup SDK environment")
        is_sdk_tar = True if "/tmp/sdk" in result.output else False
        self.assertTrue(is_sdk_tar, "Couldn't setup SDK environment")

        tar_sdk = result.output
        result = runCmd("%s --version" % tar_sdk)
        self.assertEqual(0, result.status, "Couldn't run tar from SDK")


class TestImage(oeSelfTest):

    def test_testimage_install(self):
        """
        Summary: Check install packages functionality for testimage/testexport.
        Expected: 1. Import tests from a directory other than meta.
                  2. Check install/uninstall of socat.
        Product: oe-core
        Author: Mariano Lopez <mariano.lopez@intel.com>
        """
        if get_bb_var('DISTRO') == 'poky-tiny':
            self.skipTest('core-image-full-cmdline not buildable for poky-tiny')

        features = 'INHERIT += "testimage"\n'
        features += 'TEST_SUITES = "ping ssh selftest"\n'
        self.write_config(features)

        # Build core-image-sato and testimage
        bitbake('core-image-full-cmdline socat')
        bitbake('-c testimage core-image-full-cmdline')

class Postinst(oeSelfTest):
    @testcase(1540)
    def test_verify_postinst(self):
        """
        Summary: The purpose of this test is to verify the execution order of postinst Bugzilla ID: [5319]
        Expected :
        1. Compile a minimal image.
        2. The compiled image will add the created layer with the recipes postinst[ abdpt]
        3. Run qemux86
        4. Validate the task execution order
        Author: Francisco Pedraza <francisco.j.pedraza.gonzalez@intel.com>
        """
        features = 'INHERIT += "testimage"\n'
        features += 'CORE_IMAGE_EXTRA_INSTALL += "postinst-at-rootfs \
postinst-delayed-a \
postinst-delayed-b \
postinst-delayed-d \
postinst-delayed-p \
postinst-delayed-t \
"\n'
        self.write_config(features)

        bitbake('core-image-minimal -f ')

        postinst_list = ['100-postinst-at-rootfs',
                         '101-postinst-delayed-a',
                         '102-postinst-delayed-b',
                         '103-postinst-delayed-d',
                         '104-postinst-delayed-p',
                         '105-postinst-delayed-t']
        path_workdir = get_bb_var('WORKDIR','core-image-minimal')
        workspacedir = 'testimage/qemu_boot_log'
        workspacedir = os.path.join(path_workdir, workspacedir)
        rexp = re.compile("^Running postinst .*/(?P<postinst>.*)\.\.\.$")
        with runqemu('core-image-minimal') as qemu:
            with open(workspacedir) as f:
                found = False
                idx = 0
                for line in f.readlines():
                    line = line.strip().replace("^M","")
                    if not line: # To avoid empty lines
                        continue
                    m = rexp.search(line)
                    if m:
                        self.assertEqual(postinst_list[idx], m.group('postinst'), "Fail")
                        idx = idx+1
                        found = True
                    elif found:
                        self.assertEqual(idx, len(postinst_list), "Not found all postinsts")
                        break

    @testcase(1545)
    def test_postinst_roofs_and_boot(self):
        """
        Summary:        The purpose of this test case is to verify Post-installation
                        scripts are called when roofs is created and also test
                        that script can be delayed to run at first boot.
        Dependencies:   NA
        Steps:          1. Add proper configuration to local.conf file
                        2. Build a "core-image-minimal" image
                        3. Verify that file created by postinst_rootfs recipe is
                           present on rootfs dir.
                        4. Boot the image created on qemu and verify that the file
                           created by postinst_boot recipe is present on image.
                        5. Clean the packages and image created to test with
                           different package managers
        Expected:       The files are successfully created during rootfs and boot
                        time for 3 different package managers: rpm,ipk,deb and
                        for initialization managers: sysvinit and systemd.

        """
        file_rootfs_name = "this-was-created-at-rootfstime"
        fileboot_name = "this-was-created-at-first-boot"
        rootfs_pkg = 'postinst-at-rootfs'
        boot_pkg = 'postinst-delayed-a'
        #Step 1
        features = 'MACHINE = "qemux86"\n'
        features += 'CORE_IMAGE_EXTRA_INSTALL += "%s %s "\n'% (rootfs_pkg, boot_pkg)
        features += 'IMAGE_FEATURES += "ssh-server-openssh"\n'
        for init_manager in ("sysvinit", "systemd"):
            #for sysvinit no extra configuration is needed,
            if (init_manager is "systemd"):
                features += 'DISTRO_FEATURES_append = " systemd"\n'
                features += 'VIRTUAL-RUNTIME_init_manager = "systemd"\n'
                features += 'DISTRO_FEATURES_BACKFILL_CONSIDERED = "sysvinit"\n'
                features += 'VIRTUAL-RUNTIME_initscripts = ""\n'
            for classes in ("package_rpm package_deb package_ipk",
                            "package_deb package_rpm package_ipk",
                            "package_ipk package_deb package_rpm"):
                features += 'PACKAGE_CLASSES = "%s"\n' % classes
                self.write_config(features)

                #Step 2
                bitbake('core-image-minimal')

                #Step 3
                file_rootfs_created = os.path.join(get_bb_var('IMAGE_ROOTFS',"core-image-minimal"),
                                                   file_rootfs_name)
                found = os.path.isfile(file_rootfs_created)
                self.assertTrue(found, "File %s was not created at rootfs time by %s" % \
                                (file_rootfs_name, rootfs_pkg))

                #Step 4
                testcommand = 'ls /etc/'+fileboot_name
                with runqemu('core-image-minimal') as qemu:
                    sshargs = '-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'
                    result = runCmd('ssh %s root@%s %s' % (sshargs, qemu.ip, testcommand))
                    self.assertEqual(result.status, 0, 'File %s was not created at firts boot'% fileboot_name)

                #Step 5
                bitbake(' %s %s -c cleanall' % (rootfs_pkg, boot_pkg))
                bitbake('core-image-minimal -c cleanall')
